"""Experiment T1/T2 (2026-11-07): pick the 40 rows and split them into a BLIND rows file and a scoring-only key file.

    python experiments/research_path_bakeoff/select_rows.py [--today YYYY-MM-DD] [--n 40]

ROWS. (1) Every person-confirmed event of docs/qa/answer-key.csv that is on an approved file (`<Market>_audited.final.csv`) AND on the research
input list (`<Market>_input.csv`, joined on EVENT_ID_CANON through identity.to_canonical). (2) Then the live rows with a deadline ahead, in the
order scripts/shadow_finder.select_events uses (soonest deadline first, undated after), until --n rows.
KEY (scoring only, never shown to an arm): the person-confirmed SUBMISSION DEADLINE of the answer key, else the customer-verified deadline that
agrees with ours (scripts/board_metrics.customer_agreement, live and agree), else the SHIPPED value of the approved file. key_source says which.
Writes rows.json (blind), key.json (scoring), rows.md (the list, no key values). Read-only: opens the live database with sqlite3 selects only.
Reuses scripts/shadow_finder.select_events, scripts/board_metrics.customer_agreement, src/cfp_monitor/identity (seed_map, to_canonical)."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from scripts.board_metrics import LIVE_DB, customer_agreement          # noqa: E402
from scripts.shadow_finder import MARKETS_DIR, host_of, select_events  # noqa: E402
from src.cfp_monitor.identity import seed_map, to_canonical           # noqa: E402

MARKETS = ("Cybersecurity", "Utility")


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def held_urls(fin: dict) -> dict:
    """What we already hold for the row: the page we cite for the deadline, the call page, the home page. Never the deadline value."""
    return {
        "evidence": (fin.get("DEADLINE_EVIDENCE_URL") or "").strip(),
        "cfp": (fin.get("CFP_SUBMISSION_URL") or fin.get("SUBMISSION URL") or "").strip(),
        "home": (fin.get("MAIN_INFO_URL") or fin.get("CONFERENCE URL") or "").strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    up_to_canon, roots = seed_map(str(LIVE_DB))
    if not up_to_canon:
        sys.exit(f"empty seed map (looked in {roots}): refusing to join on nothing")
    finals, inputs = [], {}
    for m in MARKETS:
        for r in read_csv(MARKETS_DIR / f"{m}_audited.final.csv"):
            r["_market"] = m
            r["_canon"] = to_canonical((r.get("EVENT_ID") or "").strip(), up_to_canon)
            finals.append(r)
        for r in read_csv(MARKETS_DIR / f"{m}_input.csv"):
            c = (r.get("EVENT_ID_CANON") or "").strip()
            if c:
                inputs.setdefault(c, dict(r, _market=m))
    by_canon = {}
    for r in finals:
        by_canon.setdefault(r["_canon"], r)
    key_rows = read_csv(ROOT / "docs" / "qa" / "answer-key.csv")
    person = {}
    for r in key_rows:
        if r["tier"] == "person-confirmed":
            person.setdefault(r["canonical"], r["event"])
    key_deadline = {r["canonical"]: r["confirmed_value"] for r in key_rows if r["tier"] == "person-confirmed" and r["field"] == "SUBMISSION DEADLINE"}
    cust = {d["event_id"]: d["ours"] for d in customer_agreement(str(LIVE_DB), a.today)["detail"] if d["live"] and d["class"] == "agree" and d["ours"]}

    chosen, why_in = [], {}
    for c in sorted(person):
        if c in by_canon and c in inputs:
            chosen.append(c)
            why_in[c] = "person-confirmed event"
        else:
            print(f"  skip person-confirmed {person[c]}: {'not on an approved file' if c not in by_canon else 'not on the input list'}")
    live = select_events([r for r in finals], a.today, 500)
    for e in live:
        if len(chosen) >= a.n:
            break
        c = to_canonical(e["id"], up_to_canon)
        if c in chosen or c not in inputs or c not in by_canon:
            continue
        chosen.append(c)
        why_in[c] = "live row, deadline ahead" if e["ours"] and e["ours"] >= a.today else "live row, no deadline held"
    rows, key, md = [], {}, ["# Rows of experiment T1/T2 (selected " + a.today + ")", "", "| # | market | event | why | held deadline page |", "|---|---|---|---|---|"]
    for i, c in enumerate(chosen, 1):
        fin, inp = by_canon[c], inputs[c]
        shipped = (fin.get("SUBMISSION DEADLINE") or "").strip()[:10]
        if c in key_deadline:
            k, src = key_deadline[c], "person-confirmed"
        elif c in cust:
            k, src = cust[c][:10], "customer-verified-agrees"
        else:
            k, src = shipped, "shipped"
        urls = held_urls(fin)
        hosts = sorted({h for h in (host_of(urls["home"]), host_of(urls["cfp"]), host_of(urls["evidence"])) if h})
        rows.append({"n": i, "canonical": c, "event": fin.get("CONFERENCE", ""), "market": fin["_market"], "edition": (fin.get("EDITION") or "").strip(),
                     "why_in": why_in[c], "held": urls, "hosts": hosts, "input_row": {k2: v for k2, v in inp.items() if not k2.startswith("_")}})
        key[c] = {"event": fin.get("CONFERENCE", ""), "key": k, "key_source": src, "shipped": shipped, "key_live": bool(k) and k >= a.today,
                  "shipped_status": (fin.get("STATUS") or "").strip(), "shipped_evidence_url": urls["evidence"]}
        md.append(f"| {i} | {fin['_market']} | {fin.get('CONFERENCE', '')} | {why_in[c]} | {urls['evidence'] or '(none)'} |")
    (HERE / "rows.json").write_text(json.dumps({"today": a.today, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    (HERE / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False), encoding="utf-8")
    (HERE / "rows.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    from collections import Counter
    print(f"{len(rows)} rows: {dict(Counter(r['why_in'] for r in rows))}; key sources {dict(Counter(v['key_source'] for v in key.values()))}; "
          f"keys ahead of today {sum(1 for v in key.values() if v['key_live'])}; blank keys {sum(1 for v in key.values() if not v['key'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
