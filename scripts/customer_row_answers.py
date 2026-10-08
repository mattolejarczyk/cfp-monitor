"""One line per customer row: an ANSWER and its REASON; plus the customer's row as research context (ACT-54, fixes c and d). READ-ONLY; always exits 0.

    python scripts/customer_row_answers.py [--today 2026-10-08] [--db <db>] [--markets-dir <dir>] [--out-dir <dir>] [--propose-context ctx.csv]

WHY (Hack In The Box, 2026-10-06). The customer's row fed only its STATUS into our process; its name, place and date never reached research, so research relied on upstream's
assumption of what the event 'typically' does, and nothing required an answer and a reason for every customer row. A row that is unmatched or wrongly matched silently dropped out
of what the customer sees.

(d) THE ANSWER LINE. For EVERY customer row (table client_conferences, opened mode=ro), exactly one line with an answer and the reason for it:
    RESEARCHED         in the research queue; the reason carries the event we hold (status, deadline, how it was verified)
    DISAGREES          researched, but the event we hold is not the event the customer means (date more than 30 days off, or another city): 'your sheet says X, we found Y'
    OVER               the event is over; the reason says whether the NEXT edition is announced (a later-dated row of the same series in our database) or 'next edition not announced'
    EXCLUDED (ruling)  in docs/operations/customer_not_researched.csv: the operator's reason, who ruled and when
    EXCLUDED (other)   removed by the customer, or only a DUP_OF input row matches
    NO ANSWER          NOT in the research queue and not excluded: a GAP. The count must be zero; the customer_coverage.py rule decides, this file only reports it.
The classification (in queue / excluded / not) is customer_coverage.check(): one rule, not a second copy.

(c) THE CUSTOMER'S ROW AS RESEARCH CONTEXT. `context_text(row)` produces the text of ONE proposed input-list column, CUSTOMER_ROW, for every input row that a customer row
pairs with (by canonical id, else same URL and a date within 30 days: the coverage rule). Format, one cell:
    CUSTOMER ROW (context, not evidence) - Arnica sheet: name "Hack In The Box" | url https://conference.hitb.org | place Alila SCBD, Jakarta, Indonesia | start 04/29/2026.
    If the event's own page differs, write both in STATUS DETAILS as: Your sheet says <place, date>; we found <place, date>.
`--propose-context ctx.csv` writes market, EVENT_ID_CANON, CONFERENCE, CUSTOMER_ROW: a PROPOSAL. Live input lists are NOT edited; the reviewer decides when the column goes in and
when the research prompt starts reading it. `page_wording(row, fact)` is the customer-page sentence for a disagreement (the page builder is not touched here).

Output: one summary line on stdout (read by nobody yet; ready for the recap)
    CUSTOMER ROWS: <n> rows; <r> researched; <d> DISAGREE; <o> over; <x> excluded; <g> NO ANSWER
plus customer_rows.md / customer_rows.json under runs_out/qa/<today>/ (INTERNAL QA, not for the customer)."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import customer_coverage as cc                                # noqa: E402
from scripts.stamp_given_ids import iso_of, norm_url                       # noqa: E402
from src.cfp_monitor import identity, qa_report                            # noqa: E402

CLIENT_LABEL = {"arnica": "Arnica", "utility-global": "Utility Global"}
CONTEXT_COLS = ["market", "EVENT_ID_CANON", "CONFERENCE", "CUSTOMER_ROW"]


def series_of(event_id: str) -> str:
    """The conference across all years: the canonical id without its leading year (same rule as match_customer_sheet.series)."""
    return re.sub(r"^(19|20)\d{2}-", "", event_id or "")


def context_text(row: dict) -> str:
    """The customer's row as one cell of research context. Only what the customer wrote about the EVENT: name, URL, place, date. Their status is the customer's and stays out."""
    label = CLIENT_LABEL.get(row.get("client_key", ""), row.get("client_key", "customer"))
    parts = [f'name "{(row.get("their_name") or "").strip()}"']
    for key, field in (("url", "their_url"), ("place", "location"), ("start", "event_start_date")):
        v = (row.get(field) or "").strip()
        if v:
            parts.append(f"{key} {v}")
    return (f"CUSTOMER ROW (context, not evidence) - {label} sheet: " + " | ".join(parts)
            + ". If the event's own page differs, write both in STATUS DETAILS as: Your sheet says <place, date>; we found <place, date>.")


def page_wording(row: dict, fact: dict | None) -> str:
    """The customer-page sentence when the event we found is not what their row says; '' when it agrees or cannot be judged."""
    if not fact or not cc.disagreement(row, fact, ""):
        return ""
    said = ", ".join(x for x in ((row.get("location") or "").strip(), (row.get("event_start_date") or "").strip()) if x) or "no place or date"
    found = ", ".join(x for x in ((fact.get("city") or "").strip(), (fact.get("start_date") or "").strip()) if x) or "no place or date"
    return f"Your sheet says {said}; we found {found} ({(fact.get('name') or '').strip()})."


def context_rows(rows: list[dict], inputs: dict[str, list[dict]], up_to_canon: dict[str, str]) -> list[dict]:
    """For each input row of a market that a customer row pairs with: its CUSTOMER_ROW cell. Pairing = coverage rule (canonical id, else URL plus a date within 30 days).
    Customer rows the customer removed are skipped. One input row, several customer rows: the cells are joined."""
    out: dict[tuple, dict] = {}
    for r in rows:
        market = cc.CLIENT_MARKET.get(r.get("client_key"))
        if market is None or market not in inputs or int(r.get("withdrawn_by_customer") or 0):
            continue
        eid = identity.to_canonical((r.get("event_id") or "").strip(), up_to_canon)
        url, start = norm_url(r.get("their_url") or ""), iso_of(r.get("event_start_date") or "")
        for i, inp in enumerate(inputs[market]):
            if (inp.get("DUP_OF") or "").strip():
                continue
            iid = identity.to_canonical((inp.get("EVENT_ID_CANON") or "").strip(), up_to_canon)
            hit = bool(eid and iid and eid == iid)
            if not hit and url and norm_url(inp.get("CONFERENCE URL", "")) == url:
                gap = cc.days_apart(start, iso_of(inp.get("START DATE") or "")) if start and iso_of(inp.get("START DATE") or "") else None
                hit = gap is None or gap <= cc.DATE_TOLERANCE_DAYS
            if hit:
                k = (market, i)
                cell = context_text(r)
                if k in out:
                    out[k]["CUSTOMER_ROW"] += " || " + cell
                else:
                    out[k] = {"market": market, "EVENT_ID_CANON": (inp.get("EVENT_ID_CANON") or "").strip(), "CONFERENCE": (inp.get("CONFERENCE") or "").strip(), "CUSTOMER_ROW": cell}
    return list(out.values())


def next_edition(event_id: str, facts: dict, today: str) -> str:
    """'<id> (<start>)' of a later-dated row of the same series that is still ahead, else ''."""
    s = series_of(event_id)
    if not s:
        return ""
    best = ""
    for eid, f in facts.items():
        if eid != event_id and series_of(eid) == s:
            d = iso_of(f.get("start_date") or "")
            if d and d >= today and (not best or d < best[1]):
                best = (eid, d)
    return f"{best[0]} ({best[1]})" if best else ""


def reason_for_event(fact: dict) -> str:
    bits = [f"status {fact.get('status') or '(blank)'}"]
    if fact.get("deadline"):
        bits.append(f"deadline {fact['deadline']}")
    bits.append("verified: " + (fact.get("verify_state") or "not recorded"))
    if fact.get("imported_at"):
        bits.append(f"loaded {str(fact['imported_at'])[:10]}")
    return ", ".join(bits)


def answers(res: dict, facts: dict, up_to_canon: dict[str, str], today: str) -> list[dict]:
    """One dict per customer row of `res` (customer_coverage.check output): client, name, answer, reason."""
    out = []
    dis = {(d["client"], d["name"]): d for d in res.get("disagree", [])}
    groups = [("in_queue", None), ("excluded", None), ("not_in_queue", None)]
    for key, _ in groups:
        for x in res[key]:
            row = x["_row"]
            eid = identity.to_canonical((x["event_id"] or "").strip(), up_to_canon)
            fact = facts.get(eid) if eid else None
            base = {"client": x["client"], "market": x["market"], "name": x["name"], "customer_url": x["url"], "customer_place": row.get("location") or "", "customer_start": x["start"],
                    "event_id": x["event_id"]}
            d = dis.get((x["client"], x["name"]))
            if d and not x["why"].startswith("operator's ledger"):                  # a wrong link wins over 'over': the customer's date may be the stale one (Hack In The Box: postponed, not over)
                ans = "DISAGREES"
                why = (f"your sheet says {d['customer_location'] or '(no place)'}, {d['customer_start'] or '(no date)'}; we found {d['event_city'] or '(no city)'}, {d['event_start'] or '(no date)'} "
                       f"({d['event_name']}): {d['why']}. A person decides which side is right; the link is not certain.")
            elif key == "in_queue":
                if fact:
                    ans, why = "RESEARCHED", f"in the research queue ({x['why']}); we hold {eid}: {reason_for_event(fact)}"
                else:
                    ans, why = "RESEARCHED", f"in the research queue ({x['why']}); no event of ours is linked to this row yet, so there is nothing to compare"
            elif key == "excluded":
                w = x["why"]
                if w.startswith("event is over"):
                    nxt = next_edition(eid, facts, today) if eid else ""
                    ans, why = "OVER", w + "; " + (f"next edition: {nxt}" if nxt else "next edition not announced (no later-dated row of this series in our database)")
                elif w.startswith("operator's ledger"):
                    ans, why = "EXCLUDED (ruling)", w
                else:
                    ans, why = "EXCLUDED (other)", w
            else:
                ans, why = "NO ANSWER", "not in the research queue and not excluded: " + x["why"]
            out.append({**base, "answer": ans, "reason": why})
    out.sort(key=lambda a: (a["client"], a["name"].lower()))
    return out


def summary_line(lines: list[dict]) -> str:
    n = lambda a: sum(1 for x in lines if x["answer"] == a)
    return (f"CUSTOMER ROWS: {len(lines)} rows; {n('RESEARCHED')} researched; {n('DISAGREES')} DISAGREE; {n('OVER')} over; "
            f"{n('EXCLUDED (ruling)') + n('EXCLUDED (other)')} excluded; {n('NO ANSWER')} NO ANSWER")


def markdown(lines: list[dict], today: str, degraded: list[str]) -> str:
    L = ["# Customer rows: one answer and one reason each (INTERNAL QA)", "", f"Date: {today}. Read-only (scripts/customer_row_answers.py). Not for the customer.", "", f"- {summary_line(lines)}"]
    L += [f"- DEGRADED: {d}" for d in degraded] + [""]
    L += ["| client | customer row | their place | their date | answer | reason |", "|---|---|---|---|---|---|"]
    for a in lines:
        L.append(f"| {a['client']} | {a['name']} | {a['customer_place'] or '-'} | {a['customer_start'] or '-'} | {a['answer']} | {a['reason'].replace('|', '/')} |")
    return "\n".join(L) + "\n"


def load(db: Path, markets_dir: Path, ledger_path: Path, today: str):
    """-> (result, facts, rows, inputs, up_to_canon, degraded) or raises ValueError(why). Opens the database mode=ro."""
    if not Path(db).exists():
        raise ValueError(f"database not found ({db})")
    up_to_canon, roots = identity.seed_map(str(db))
    degraded = [] if up_to_canon else ["the event-id seed map is empty: ids are compared as spelled"]
    inputs = {}
    for market in cc.CLIENT_MARKET.values():
        p = Path(markets_dir) / f"{market}_input.csv"
        if not p.exists():
            raise ValueError(f"input list not found ({p})")
        inputs[market] = cc.read_csv(p)
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("select * from client_conferences")]
        facts = {r["event_id"]: dict(r) for r in con.execute("select * from grounding_facts")}
    except sqlite3.Error as e:
        raise ValueError(f"database could not be read ({e})")
    finally:
        con.close()
    if not rows:
        raise ValueError("client_conferences is empty")
    res = cc.check(rows, inputs, up_to_canon, cc.load_ledger(ledger_path), today, facts)
    return res, facts, rows, inputs, up_to_canon, degraded


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--db", default=str(cc.LIVE_DB))
    ap.add_argument("--markets-dir", default=str(cc.MARKETS))
    ap.add_argument("--ledger", default=str(cc.NOT_RESEARCHED))
    ap.add_argument("--out-dir", default="", help="default runs_out/qa/<today>")
    ap.add_argument("--propose-context", default="", help="write the proposed CUSTOMER_ROW input-list column as a CSV (live input lists are NOT edited)")
    a = ap.parse_args()
    try:
        res, facts, rows, inputs, up_to_canon, degraded = load(Path(a.db), Path(a.markets_dir), Path(a.ledger), a.today)
        lines = answers(res, facts, up_to_canon, a.today)
        for d in degraded:
            print(f"CUSTOMER ROWS DEGRADED: {d}")
        print(summary_line(lines))
        for g in [x for x in lines if x["answer"] == "NO ANSWER"][:5]:
            print(f"CUSTOMER ROWS NO ANSWER: {g['name']}")
        out_dir = Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "customer_rows.json").write_text(json.dumps({"today": a.today, "summary": summary_line(lines), "degraded": degraded, "rows": lines}, indent=1, ensure_ascii=True), encoding="utf-8")
        (out_dir / "customer_rows.md").write_text(markdown(lines, a.today, degraded), encoding="utf-8")
        if a.propose_context:
            ctx = context_rows(rows, inputs, up_to_canon)
            with open(a.propose_context, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=CONTEXT_COLS, lineterminator="\n")
                w.writeheader()
                w.writerows(ctx)
            print(f"CUSTOMER ROWS: {len(ctx)} proposed CUSTOMER_ROW cell(s) written to {a.propose_context}")
    except ValueError as e:
        print(f"CUSTOMER ROWS: UNKNOWN - {e}")
    except Exception as e:                                                  # a QA report must never stop the Saturday job
        print(f"CUSTOMER ROWS: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
