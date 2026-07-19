"""Batch runner: process a folder of market list workbooks one file at a time.

Two phases on purpose, so a human confirms BEFORE anything crawls:

    plan  -> scan the folder, propose a market per file, write a manifest you can review
    run   -> validate every row, then crawl each file in turn, unattended

`run` refuses to start while any row is unresolved, so a bad label fails in second zero
rather than three hours into an overnight sweep. Each file becomes its own run (its own
input-audit ledger + industry), and the manifest records per-file status so an interrupted
batch resumes where it stopped.

Usage:
    python scripts/run_batch.py plan  [--folder DIR] [--manifest FILE]
    python scripts/run_batch.py run   [--manifest FILE] [--stop-on-error]
    python scripts/run_batch.py markets [--add NAME] [--force]
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor import run_urls, Settings                      # noqa: E402
from src.cfp_monitor.markets import MarketRegistry, parse_filename   # noqa: E402
from src.cfp_monitor.quality_gate import classify_result             # noqa: E402
from src.cfp_monitor.storage import Store                            # noqa: E402
from src.cfp_monitor.uploads import (                                # noqa: E402
    normalize_urls_and_contexts_audited, uploaded_urls_and_contexts,
)

DB_PATH = os.getenv("CFP_DB_PATH", "cfp_monitor.db")
MANIFEST = "batch_manifest.csv"
FIELDS = ["file", "market", "list_type", "urls", "status", "note"]
LIST_SUFFIXES = (".xlsx", ".xlsm", ".csv", ".txt")


def _fmt(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s}s" if s < 60 else (f"{s // 60}m {s % 60}s" if s < 3600 else f"{s // 3600}h {(s % 3600) // 60}m")


def _load_file(path: Path) -> tuple[list[str], list[dict | None], dict]:
    """URLs + row contexts + the normalize/dedupe audit manifest for one list file."""
    raw, contexts = uploaded_urls_and_contexts(path.name, path.read_bytes())
    return normalize_urls_and_contexts_audited(raw, contexts)


def _read_manifest(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_manifest(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ plan ----
def cmd_plan(args) -> int:
    folder = args.folder or Settings().markets_dir
    if not folder:
        print("No folder given. Pass --folder DIR or set CFP_MARKETS_DIR in your .env.")
        return 2
    d = Path(folder)
    if not d.is_dir():
        print(f"Not a folder: {d}")
        return 2

    store = Store(DB_PATH)
    reg = MarketRegistry(store.db)
    files = sorted(p for p in d.iterdir()
                   if p.suffix.lower() in LIST_SUFFIXES and not p.name.startswith("~$"))
    if not files:
        print(f"No list files (.xlsx/.csv/.txt) in {d}")
        store.close()
        return 2

    rows: list[dict] = []
    for p in files:
        candidate, list_type = parse_filename(p.name)
        market = reg.resolve(candidate) or ""
        try:
            urls, _, _man = _load_file(p)
            n, note = len(urls), ""
        except Exception as e:
            n, note = 0, f"unreadable: {type(e).__name__}"
        status = "ready" if market and n else "NEEDS_INPUT"
        if market and not n:
            note = note or "no URLs found"
        if not market:
            note = note or f"unmatched name '{candidate}' - pick a market"
        rows.append({"file": str(p), "market": market, "list_type": list_type or "",
                     "urls": n, "status": status, "note": note})

    _write_manifest(args.manifest, rows)
    known = reg.all()
    store.close()

    fw = max(len(Path(r["file"]).name) for r in rows)
    mw = max(max(len(r["market"]) for r in rows), len("MARKET"))
    print(f"\nScanned {len(rows)} file(s) in {d}\n")
    print(f"  {'FILE'.ljust(fw)}  {'MARKET'.ljust(mw)}  {'TYPE'.ljust(11)} {'URLS':>5}  STATUS")
    for r in rows:
        print(f"  {Path(r['file']).name.ljust(fw)}  {(r['market'] or '-').ljust(mw)}  "
              f"{(r['list_type'] or '-').ljust(11)} {str(r['urls']):>5}  {r['status']}"
              + (f"   ({r['note']})" if r["note"] else ""))

    # Report the two blockers separately - they need different fixes.
    needs_market = [r for r in rows if not r["market"]]
    no_urls = [r for r in rows if r["market"] and not int(r["urls"] or 0)]
    ready = [r for r in rows if r["status"] == "ready"]
    print(f"\nManifest written: {args.manifest}")
    print(f"{len(ready)} of {len(rows)} file(s) ready ({sum(int(r['urls']) for r in ready)} URLs).")
    if needs_market:
        print(f"\n{len(needs_market)} file(s) need a MARKET:")
        for r in needs_market:
            print(f"  - {Path(r['file']).name}")
        print(f"  Known markets: {', '.join(known)}")
        print(f"  Set the 'market' column in {args.manifest}, or add a genuinely new one:")
        print('    python scripts/run_batch.py markets --add "Name"')
    if no_urls:
        print(f"\n{len(no_urls)} file(s) have a market but NO usable URLs - these are skipped:")
        for r in no_urls:
            print(f"  - {Path(r['file']).name}")
        print("  We only take literal URLs from the designated URL column; a different")
        print("  workbook layout (e.g. award lists) will read as empty rather than guess.")
    if ready and not needs_market:
        print(f"\nStart the sweep:  python scripts/run_batch.py run --manifest {args.manifest}")
    return 0


# ------------------------------------------------------------------- run ----
def cmd_run(args) -> int:
    if not Path(args.manifest).exists():
        print(f"No manifest at {args.manifest} - run 'plan' first.")
        return 2
    rows = _read_manifest(args.manifest)
    store = Store(DB_PATH)
    reg = MarketRegistry(store.db)

    # --- validation gate: nothing crawls until every pending row is sound ---
    problems: list[str] = []
    for r in rows:
        if r["status"] == "done":
            continue
        name = Path(r["file"]).name
        canonical = reg.resolve(r["market"])
        if not r["market"]:
            problems.append(f"{name}: no market set")
        elif not canonical:
            problems.append(f"{name}: market '{r['market']}' is not a known market "
                            f"(add it with: markets --add \"{r['market']}\")")
        else:
            r["market"] = canonical                     # normalize spelling in-place
        if not Path(r["file"]).exists():
            problems.append(f"{name}: file no longer exists")
        elif str(r.get("urls") or "0") in ("0", ""):
            problems.append(f"{name}: 0 URLs")
    if problems:
        print("Refusing to start - fix these first:\n")
        for p in problems:
            print(f"  - {p}")
        store.close()
        return 1

    pending = [r for r in rows if r["status"] != "done"]
    if not pending:
        print("Nothing to do - every row is already done.")
        store.close()
        return 0

    total_urls = sum(int(r["urls"]) for r in pending)
    markets = sorted({r["market"] for r in pending})
    print(f"\n{len(pending)} file(s) | {total_urls} URLs | markets: {', '.join(markets)}")
    print("Crawling one file at a time. Ctrl-C is safe: finished files stay done.\n")

    settings = Settings()
    try:
        settings.require_llm_key()
    except Exception as e:
        print(f"Cannot start: {e}")
        store.close()
        return 1

    t0 = time.monotonic()
    failed = 0
    for i, r in enumerate(pending, start=1):
        p = Path(r["file"])
        print(f"[{i}/{len(pending)}] {p.name}  ({r['market']}"
              + (f" / {r['list_type']}" if r["list_type"] else "") + f", {r['urls']} URLs)")
        f0 = time.monotonic()
        try:
            urls, contexts, manifest = _load_file(p)

            def _progress(done: int, total: int, current: str | None) -> None:
                if current is not None:
                    print(f"      {done + 1}/{total}  {current.split('://', 1)[-1][:60]}", flush=True)

            results = asyncio.run(run_urls(urls, settings, contexts=contexts,
                                           on_progress=_progress, industry=r["market"]))
            run_id = store.start_run()
            counts = {"url_count": len(results)}
            for res in results:
                q = classify_result(res).verdict
                counts[q.value] = counts.get(q.value, 0) + 1
                store.upsert(res, q, run_id=run_id)
            store.finish_run(run_id, counts, industry=r["market"], input_manifest=manifest)
            r["status"], r["note"] = "done", (
                f"run {run_id}: " + " ".join(f"{k}={v}" for k, v in counts.items() if k != "url_count"))
            print(f"      done in {_fmt(time.monotonic() - f0)} - {r['note']}\n")
        except KeyboardInterrupt:
            print("\nInterrupted - progress saved. Re-run the same command to resume.")
            _write_manifest(args.manifest, rows)
            store.close()
            return 130
        except Exception as e:
            failed += 1
            r["status"], r["note"] = "failed", f"{type(e).__name__}: {e}"
            print(f"      FAILED: {r['note']}\n")
            if args.stop_on_error:
                _write_manifest(args.manifest, rows)
                store.close()
                return 1
        _write_manifest(args.manifest, rows)     # checkpoint after every file (resume-safe)

    store.close()
    print(f"Batch complete in {_fmt(time.monotonic() - t0)} - "
          f"{len(pending) - failed} succeeded, {failed} failed. Review in the app.")
    return 1 if failed else 0


# --------------------------------------------------------------- markets ----
def cmd_markets(args) -> int:
    store = Store(DB_PATH)
    reg = MarketRegistry(store.db)
    if args.add:
        try:
            name = reg.add(args.add, force=args.force)
            print(f"Market available: {name}")
        except ValueError as e:
            print(f"Refused: {e}")
            store.close()
            return 1
    print("\nKnown markets:")
    for m in reg.all():
        print(f"  - {m}")
    store.close()
    return 0


def main() -> int:
    # Line-buffer stdout: a batch is long-running and usually redirected to a log, where
    # Python's default block buffering would hide all progress until the process exits.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Crawl a folder of market lists, one file at a time.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("plan", help="scan a folder and write a reviewable manifest")
    p1.add_argument("--folder", help="folder of list workbooks (default: CFP_MARKETS_DIR)")
    p1.add_argument("--manifest", default=MANIFEST)
    p1.set_defaults(func=cmd_plan)

    p2 = sub.add_parser("run", help="crawl every file in a confirmed manifest")
    p2.add_argument("--manifest", default=MANIFEST)
    p2.add_argument("--stop-on-error", action="store_true")
    p2.set_defaults(func=cmd_run)

    p3 = sub.add_parser("markets", help="list or add markets")
    p3.add_argument("--add", help="register a genuinely new market")
    p3.add_argument("--force", action="store_true", help="allow a name close to an existing one")
    p3.set_defaults(func=cmd_markets)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
