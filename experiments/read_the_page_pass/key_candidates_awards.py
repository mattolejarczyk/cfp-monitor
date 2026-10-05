"""Answer-key CANDIDATES for the live AWARDS (ACT-22, 2026-10-05). Awards have no answer key at all, so awards accuracy has no measure. This reads each live award's own pages and writes what the
reader PROVES, set against what we ship. NOTHING is confirmed here and nothing is added to docs/qa/answer-key.csv: every line is a CANDIDATE, and the differences are listed for the operator.

    python experiments/read_the_page_pass/key_candidates_awards.py [--limit 40] [--out-dir <dir>] [--max-usd 0.10] [--dry-run]

Per live award (scripts/awards_shadow.live_awards: read-only from the awards table):
  SUBMISSION DEADLINE   the awards finder: home page + sitemap + menu -> frozen page rules -> the cheap reader asked for the ENTRY or NOMINATION deadline -> code-proven quote ->
                        the INVERTED main-call rule (a nomination or entry page IS the call). Compared with the stored deadline.
  ORGANIZER, COUNTRY    the read-the-page reader on the pages the finder read (home page and the page that gave the deadline), accepted only with a verbatim quote (pass_lib.accept).
Status per fact (same words as key_candidates.py): agree (both have it and it is the same: two routes agree), differs (ONE IS WRONG: a person looks), reader-only (we ship blank, the page states it),
unproven (we ship a value, the pages prove none: it may be right). `tier`: 'candidate: page-proven and agrees', 'candidate: DIFFERS, a person decides', 'candidate: reader-only',
'not proven'. Writes docs/qa/answer-key-AWARDS-CANDIDATES.csv and docs/qa/answer-key-AWARDS-DISAGREEMENTS.md (the list for the operator). Read-only toward the data; own request log and cost cap (default 0.10 USD)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, ROOT / "scripts", ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))

TIER = {"agree": "candidate: page-proven and agrees", "differs": "candidate: DIFFERS, a person decides", "reader-only": "candidate: reader-only (we ship blank)", "unproven": "not proven", "both-blank": "both blank"}
COLS = ["id", "event", "market", "field", "claimed", "reader_value", "status", "tier", "quote", "why", "pages"]


def status_for(field: str, claimed: str, got: str) -> str:
    from experiments.read_the_page_pass.key_candidates import compare
    return compare({"SUBMISSION DEADLINE": "start_date", "ORGANIZER": "organizer", "COUNTRY": "country"}[field], claimed, got)


def rows_for(ev: dict, rec: dict, fields: dict | None, text: str, pages_cache: dict[str, str]) -> list[dict]:
    """The candidate lines of ONE award from its finder record and the reader's answer on `text`."""
    from experiments.read_the_page_pass import pass_lib as L
    out = []
    urls = [p["url"] for p in (rec.get("pages") or []) if p.get("chars", 0) > 300][:3]
    pick = rec.get("pick") or {}
    pu = next((p for p in rec.get("pages") or [] if pick.get("pick") and p.get("accepted") == pick["pick"] and p.get("rank") != 0), {})
    got = pick.get("pick", "") or ""
    out.append({"id": ev["id"], "event": ev["event"], "market": ev["market"], "field": "SUBMISSION DEADLINE", "claimed": ev["ours"], "reader_value": got, "status": status_for("SUBMISSION DEADLINE", ev["ours"], got),
                "quote": pu.get("quote", "") if got else "", "why": "ok" if got else (pick.get("why") or "no accepted date"), "pages": pu.get("url", "") if got else " | ".join(urls)})
    for key, col, ours in (("organizer", "ORGANIZER", ev.get("organizer", "")), ("country", "COUNTRY", ev.get("country", ""))):
        item = (fields or {}).get(key) or {}
        val, why = L.accept(key, item, text, ev.get("edition") or "") if text.strip() else ("", "page unreadable")
        url = next((u for u, t in pages_cache.items() if val and item.get("quote") and L.norm(item["quote"]) in L.norm(t)), "") if val else ""
        out.append({"id": ev["id"], "event": ev["event"], "market": ev["market"], "field": col, "claimed": ours, "reader_value": val, "status": status_for(col, ours, val),
                    "quote": item.get("quote", "") if val else "", "why": "ok" if val else why, "pages": url or " | ".join(urls)})
    for r in out:
        r["tier"] = TIER[r["status"]]
    return out


def disagreements_md(rows: list[dict], meta: dict) -> str:
    from collections import Counter
    c = Counter(r["status"] for r in rows)
    lines = ["# Awards answer-key candidates: what needs the operator", "",
             f"Generated {meta['stamp']} from {meta['events']} live awards ({meta['read']} read on their own sites; cost {meta['usd']:.4f} USD). NOTHING here is confirmed: every line is a candidate and none is in "
             "`docs/qa/answer-key.csv`. To confirm one, add a pin (QA-REGISTER C14).", "",
             f"Facts: {dict(c)}.", ""]
    for kind, title in (("differs", "DIFFERS: we ship one value, the page states another (one is wrong)"), ("reader-only", "READER-ONLY: we ship blank, the page states it")):
        items = [r for r in rows if r["status"] == kind]
        lines += [f"## {title} ({len(items)})", ""]
        for r in items:
            lines.append(f"- **{r['event']}** ({r['market']}) {r['field']}: ours {r['claimed'] or '(blank)'}, page says **{r['reader_value']}**")
            lines.append(f"  - {r['pages']}  \"{r['quote'][:220]}\"")
        lines.append("")
    return "\n".join(lines)


async def run(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from scripts.awards_shadow import live_awards
    from scripts.board_metrics import LIVE_DB
    events = live_awards(a.db or LIVE_DB, a.today, a.limit)
    print(f"{len(events)} live awards", flush=True)
    if a.dry_run:
        for e in events:
            print(f"  {e['market'][:5]} {e['ours'] or '-':10} {e['event'][:52]:52} {e['home'][:60]}")
        return 0
    from experiments.finder_reader_test import run as F
    from experiments.read_the_page_pass import pass_lib as L
    from scripts.shadow_finder import build_ctx
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(a.out_dir) if a.out_dir else ROOT / "docs" / "qa"
    log_dir = Path(a.out_dir) if a.out_dir else HERE / "awards_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ctx = build_ctx(log_dir / f"awards_candidates_llm_log_{stamp}.jsonl", a.max_usd)
    R, _f = ctx.R, ctx._f
    rows, read, stopped, t0 = [], 0, "", time.time()
    for i, ev in enumerate(events, 1):
        if R.spent()[1] >= a.max_usd:
            stopped = f"stopped at the {a.max_usd} USD cap"
            break
        cache: dict[str, str] = {}
        try:
            rec = await F.find_and_read(ev, ctx, 8, "C", a.today, cache, say=lambda *x, **k: None)
        except SystemExit as e:                                           # the request log's budget guard
            stopped = f"stopped: {e}"
            break
        except Exception as e:                                            # noqa: BLE001
            rec = {"skipped": f"{type(e).__name__}: {e}"}
        if rec.get("skipped") or not any(p.get("chars", 0) > 300 for p in rec.get("pages") or []):
            print(f"  [{i}/{len(events)}] unreadable {ev['event'][:50]}: {rec.get('skipped', 'no page read')}", flush=True)
            for col in ("SUBMISSION DEADLINE", "ORGANIZER", "COUNTRY"):
                ours = {"SUBMISSION DEADLINE": ev["ours"], "ORGANIZER": ev["organizer"], "COUNTRY": ev["country"]}[col]
                rows.append({"id": ev["id"], "event": ev["event"], "market": ev["market"], "field": col, "claimed": ours, "reader_value": "", "status": "unproven" if ours else "both-blank",
                             "tier": TIER["unproven" if ours else "both-blank"], "quote": "", "why": str(rec.get("skipped", "page unreadable")), "pages": ev["home"]})
            continue
        pick_url = next((p["url"] for p in rec["pages"] if (rec.get("pick") or {}).get("pick") and p.get("accepted") == rec["pick"]["pick"] and p.get("rank") != 0), "")
        texts = [cache.get(ev["home"], ""), cache.get(pick_url, "")] if pick_url != ev["home"] else [cache.get(ev["home"], "")]
        text = "\n\n".join(t[:7000] for t in texts if t)
        fields = None
        if text.strip():
            try:
                fields, _c = R.ask(a.model, ev["event"], ev["edition"] or a.today[:4], text)
            except SystemExit as e:
                stopped = f"stopped: {e}"
                break
        rows += rows_for(ev, rec, fields or {}, text, cache)
        read += 1
        print(f"  [{i}/{len(events)}] {ev['event'][:50]:50} {', '.join(r['status'] for r in rows[-3:])}", flush=True)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                     # noqa: BLE001
        pass
    meta = {"stamp": stamp, "events": len(events), "read": read, "usd": R.spent()[1], "minutes": (time.time() - t0) / 60, "stopped": stopped}
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "answer-key-AWARDS-CANDIDATES.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    (out_dir / "answer-key-AWARDS-DISAGREEMENTS.md").write_text(disagreements_md(rows, meta), encoding="utf-8")
    from collections import Counter
    print(f"{read} awards read, {len(rows)} facts: {dict(Counter(r['status'] for r in rows))}; {meta['minutes']:.0f} min, {meta['usd']:.4f} USD{'; ' + stopped if stopped else ''} -> {out_dir}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--model", default="C")
    ap.add_argument("--db", help="database to read the awards from (read-only; default the live one)")
    ap.add_argument("--out-dir", help="write the CSV, the list and the request log here instead of docs/qa")
    ap.add_argument("--max-usd", type=float, default=0.10)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
