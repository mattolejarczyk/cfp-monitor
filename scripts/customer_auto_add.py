"""Weekly route that puts the customer rows NOT in the research queue onto the input lists (ACT-51 phase 2). DRY RUN unless --apply; always exits 0.

    python scripts/customer_auto_add.py [--today D] [--db <db>] [--markets-dir <dir>] [--out-dir <dir>] [--cap 10] [--apply [--live]]

WHY. Phase 1 (scripts/customer_coverage.py) REPORTS which customer rows ahead of today are not on `Markets/<Market>_input.csv`. This is the step that closes the gap, by the rules of
docs/design/ACT-51-auto-add-design.md: a GATE sorts each missing row into ADD or HOLD FOR A PERSON; only ADD rows are appended (by scripts/add_customer_rows.py, the existing and only writer,
with its backup and read-back proof) with a BLANK EVENT_ID_CANON. We never mint an id and never join on one: coverage pairs by identity.to_canonical or URL plus date.

THE GATE (each HOLD names its reason; HOLD rows are listed, never changed):
  * linked but missing: the customer row is already linked to an event we hold (event_id set) yet no input row carries it. Adding a second row for a held event starts duplicates. A person decides
    (put the held event on the list by stamping its canonical id, or rule it out in docs/operations/customer_not_researched.csv).
  * edition guard: an input row of that market is on the SAME WEBSITE (registered domain) but coverage did not pair it (another year, or a date more than 30 days away). It may be another edition
    or the same event with a wrong date (Gartner IAM, OWASP, Hack In The Box). A person decides.
  * no URL: nothing to start the research from, and no way to tell the edition.
  * cap: more than --cap (10) ADD rows for one market in one run means the sheet changed shape or the matcher broke: that market adds NOTHING and says so.
  * add_customer_rows.plan skips: a name already on the list (under another URL), or an event starting before today.

OUTPUT (out-dir, default runs_out/qa/<today>): proposed_additions.csv (the ADD rows in the class-C layout, readable by add_customer_rows.py), auto_add.json and auto_add.md (every ADD and HOLD
with reasons), request_to_upstream_<today>.md (a DRAFT asking upstream for the ids of the rows that still have none: the operator sends it, code sends nothing). stdout, read by weekend_recap.py:
    AUTOADD: mode=dry-run|applied; <a> to add|added, <h> held for a person, <w> waiting for an id; <k> customer rows NOT in the queue after the step
    AUTOADD HELD: <first five names>      (only when h > 0)
    AUTOADD NOT PICKED UP: <first five names>   (only when mode=applied and k > 0)

--apply writes the input lists. It refuses the live Markets folder unless --live is also given (the reviewer's switch). Never touches the database (opened read-only by customer_coverage)."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import add_customer_rows as acr                                  # noqa: E402
from scripts import customer_coverage as cc                                   # noqa: E402
from src.cfp_monitor import qa_report                                         # noqa: E402

CAP_PER_MARKET = 10
SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}
SHEET_MARKET = acr.SHEET_MARKET


def registered_domain(url: str) -> str:
    """'https://www.conf.example.co.uk/2027' -> 'example.co.uk'; '' when there is no host."""
    u = (url or "").strip()
    host = (urlparse(u if "//" in u else "//" + u).hostname or "").lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return host
    keep = 3 if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2 else 2
    return ".".join(parts[-keep:])


def gate(not_in: list[dict], inputs: dict[str, list[dict]], cap: int = CAP_PER_MARKET) -> tuple[list[dict], list[tuple[dict, str]]]:
    """-> (ADD rows in the class-C layout, [(missing item, HOLD reason)])."""
    add: list[dict] = []
    hold: list[tuple[dict, str]] = []
    by_domain: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for market, rows in inputs.items():
        d = by_domain.setdefault(market, {})
        for r in rows:
            dom = registered_domain(r.get("CONFERENCE URL", ""))
            if dom:
                d.setdefault(dom, []).append(((r.get("CONFERENCE") or "").strip(), acr.iso_of(r.get("START DATE") or "")))
    cand = cc.propose_rows({"not_in_queue": not_in})
    per_market: dict[str, list[tuple[dict, dict]]] = {}
    for item, row in zip(not_in, cand):
        market = item["market"]
        if (item.get("event_id") or "").strip():
            hold.append((item, "linked to an event we hold (" + item["event_id"] + ") but no input row carries it: a person puts the held event on the list or rules it out"))
            continue
        if not (item.get("url") or "").strip():
            hold.append((item, "no URL: nothing to start the research from and no way to tell the edition"))
            continue
        dom = registered_domain(item["url"])
        near = by_domain.get(market, {}).get(dom, [])
        if near:
            seen = "; ".join(f"{n} ({s or 'no date'})" for n, s in near[:3])
            hold.append((item, f"edition guard: the input list already has this website ({dom}): {seen}; customer date {item.get('start') or 'none'}. Another edition or a wrong date: a person decides"))
            continue
        per_market.setdefault(market, []).append((item, row))
    for market, pairs in per_market.items():
        if len(pairs) > cap:
            for item, _ in pairs:
                hold.append((item, f"cap: {len(pairs)} rows for {market} this run, above {cap}: the sheet changed shape or the matcher broke; nothing is added for this market"))
        else:
            add.extend(r for _, r in pairs)
    return add, hold


def waiting_for_id(inputs: dict[str, list[dict]]) -> list[dict]:
    """Input rows with a blank EVENT_ID_CANON that are not marked DUP_OF: researched but never loaded as a new event until upstream gives the id."""
    out = []
    for market, rows in inputs.items():
        for r in rows:
            if not (r.get("EVENT_ID_CANON") or "").strip() and not (r.get("DUP_OF") or "").strip():
                out.append({"market": market, "name": (r.get("CONFERENCE") or "").strip(), "url": (r.get("CONFERENCE URL") or "").strip(), "start": (r.get("START DATE") or "").strip()})
    return out


def request_draft(today: str, added: list[dict], waiting: list[dict]) -> str:
    L = [f"DRAFT request to upstream, {today} - the operator reads and sends it; nothing is sent by code.", "",
         "Please give us your permanent EVENT_ID for each event below (we research them under their URL and hold them back from the load until we have the id). If one of them is the same event as one you already track, tell us which id.", ""]
    names = {w["name"] for w in waiting} | {a["CONFERENCE"] for a in added}
    L += [f"Events without an id ({len(names)}):", "", "| market | event | start | URL |", "|---|---|---|---|"]
    seen = set()
    for a in added:
        seen.add(a["CONFERENCE"])
        L.append(f"| {a['Market']} | {a['CONFERENCE']} | {a['START DATE'] or '-'} | {a['CONFERENCE URL'] or '-'} |")
    for w in waiting:
        if w["name"] not in seen:
            L.append(f"| {w['market']} | {w['name']} | {w['start'] or '-'} | {w['url'] or '-'} |")
    return "\n".join(L) + "\n"


def run(today: str, db: Path, markets_dir: Path, ledger: Path, out_dir: Path, cap: int, apply: bool) -> tuple[list[str], int]:
    """-> (stdout lines, 0). Raises nothing the caller must handle except bugs; main() wraps."""
    res, degraded, why = cc.run(db, markets_dir, ledger, today)
    if res is None:
        return [f"AUTOADD: UNKNOWN - coverage could not run ({why})"], 0
    inputs = {m: cc.read_csv(Path(markets_dir) / f"{m}_input.csv") for m in cc.CLIENT_MARKET.values()}
    cols = {m: acr.read_input(Path(markets_dir) / f"{m}_input.csv")[0] for m in inputs}
    add_prop, hold = gate(res["not_in_queue"], inputs, cap)
    plan_add, skipped = acr.plan(add_prop, inputs, cols, today)
    for conf, reason in skipped:
        item = next((x for x in res["not_in_queue"] if x["name"] == conf), {"name": conf, "client": "", "market": "", "url": "", "start": ""})
        hold.append((item, f"not added: {reason}"))
    added_rows = [r for rows in plan_add.values() for r in rows]
    waiting = waiting_for_id(inputs)
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = {r["conference"] for r in add_prop} - {c for c, _ in skipped}
    with open(out_dir / "proposed_additions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cc.PROPOSE_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(r for r in add_prop if r["conference"] in kept)
    applied_note = []
    if apply:
        files = {m: (Path(markets_dir) / f"{m}_input.csv", *acr.read_input(Path(markets_dir) / f"{m}_input.csv")) for m in inputs}
        for m, rows in plan_add.items():
            if rows:
                p, c, old, bom, crlf = files[m]
                bak = acr.write_with_proof(p, c, old, rows, bom, crlf)
                applied_note.append(f"{p.name}: {len(rows)} appended, backup {bak.name}")
        after, _, _ = cc.run(db, markets_dir, ledger, today)
        k_after, left = (len(after["not_in_queue"]), [x["name"] for x in after["not_in_queue"]]) if after else (-1, [])
        inputs_after = {m: cc.read_csv(Path(markets_dir) / f"{m}_input.csv") for m in inputs}
        waiting = waiting_for_id(inputs_after)
    else:
        k_after, left = len(res["not_in_queue"]), [x["name"] for x in res["not_in_queue"]]
    summary = {"today": today, "mode": "applied" if apply else "dry-run", "to_add": [{k: v for k, v in r.items() if k in ("Market", "CONFERENCE", "CONFERENCE URL", "START DATE", "LOCATION")} for r in added_rows],
               "held": [{"name": i["name"], "client": i.get("client", ""), "url": i.get("url", ""), "start": i.get("start", ""), "reason": r} for i, r in hold],
               "waiting_for_id": waiting, "not_in_queue_after": k_after, "applied": applied_note, "degraded": degraded}
    (out_dir / "auto_add.json").write_text(json.dumps(summary, indent=1, ensure_ascii=True), encoding="utf-8")
    md = [f"# Customer rows: automatic add ({summary['mode']}), {today}", "", f"- ADD ({len(added_rows)}), HOLD for a person ({len(hold)}), waiting for an id ({len(waiting)}), NOT in queue after the step: {k_after}", ""]
    md += ["## ADD", ""] + ([f"- {r['Market']}: {r['CONFERENCE']} | {r['START DATE'] or 'no date'} | {r['CONFERENCE URL']}" for r in added_rows] or ["None."]) + ["", "## HOLD FOR A PERSON", ""]
    md += [f"- {i['name']} ({i.get('client', '')}): {r}" for i, r in hold] or ["None."]
    (out_dir / "auto_add.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out_dir / f"request_to_upstream_{today}.md").write_text(request_draft(today, added_rows, waiting), encoding="utf-8")
    verb = "added" if apply else "to add"
    lines = [f"AUTOADD: mode={summary['mode']}; {len(added_rows)} {verb}, {len(hold)} held for a person, {len(waiting)} waiting for an id; {k_after} customer rows NOT in the queue after the step"]
    if hold:
        lines.append("AUTOADD HELD: " + "; ".join(i["name"] for i, _ in hold[:5]) + (f"; and {len(hold) - 5} more" if len(hold) > 5 else ""))
    if apply and k_after > 0:
        lines.append("AUTOADD NOT PICKED UP: " + "; ".join(left[:5]) + (f"; and {len(left) - 5} more" if len(left) > 5 else ""))
    return lines, 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--db", default=str(cc.LIVE_DB))
    ap.add_argument("--markets-dir", default=str(cc.MARKETS))
    ap.add_argument("--ledger", default=str(cc.NOT_RESEARCHED))
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--cap", type=int, default=CAP_PER_MARKET)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--live", action="store_true", help="allow --apply on the live Markets folder (the reviewer's switch)")
    a = ap.parse_args()
    try:
        if a.apply and Path(a.markets_dir).resolve() == Path(cc.MARKETS).resolve() and not a.live:
            print("AUTOADD: REFUSED - --apply on the live Markets folder needs --live (reviewer's switch); nothing written")
            return 0
        out = Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today
        lines, _ = run(a.today, Path(a.db), Path(a.markets_dir), Path(a.ledger), out, a.cap, a.apply)
        print("\n".join(lines))
    except Exception as e:                                                      # a step before the research must never stop the Saturday job
        print(f"AUTOADD: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
