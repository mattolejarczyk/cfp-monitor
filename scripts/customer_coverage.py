"""Is EVERY event on the two customer sheets in our research queue? (ACT-51, failure point A14). READ-ONLY; always exits 0.

    python scripts/customer_coverage.py [--today 2026-10-06] [--db <db>] [--markets-dir <dir>] [--out-dir <dir>] [--propose rows.csv]

WHY. The customer's sheets (Arnica = Cybersecurity, Utility Global = Utility) define the job: any event on them is researched. The research queue is the input list
`Markets/<Market>_input.csv`. Nothing used to check the two against each other, so a row the customer added never reached the queue (found 2026-10-05: 57 events ahead, not held).

THE QUESTION, per customer row (table `client_conferences`, opened `file:...?mode=ro`): is it IN THE QUEUE?
  * linked row (event_id set): `identity.to_canonical(event_id)` equals `to_canonical(EVENT_ID_CANON)` of an input row of the client's market;
  * any row, linked or not, whose normalised URL (stamp_given_ids.norm_url) equals the URL of an input row AND whose start date is within 30 days of that row's (the same website alone is
    not a pairing; a missing date on either side cannot disprove it). This is the way a freshly added row with a blank id is found.
LINKED BUT DISAGREES (a second section): a customer row linked to an event whose start date is more than 30 days from the customer's, or whose city is not named in the customer's location
(Hack In The Box: customer Jakarta 2026-04-29, linked to the Phuket event of 2026-08-24). Counted in the summary line, listed with both sides. Report only.
EXCLUSIONS, each counted and listed with its reason, never silent: the customer removed the row from their sheet (withdrawn_by_customer); the event is over (start date before today);
the row is in the operator's ledger docs/operations/customer_not_researched.csv (only the operator adds to it); the only input row it matches is marked DUP_OF.
A row with NO start date is treated as ahead (finding the date is what research is for).

OUTPUT. Two lines on stdout, read by scripts/weekend_recap.py:
    COVERAGE: <n> of <m> customer rows ahead of today are in the research queue; <k> are NOT; <j> linked rows disagree on date or place
    COVERAGE NOT IN QUEUE: <first five names>            (only when k > 0)
or `COVERAGE: UNKNOWN - <why>` when the inputs cannot be read (degraded input is reported, never fatal). Plus coverage.json and coverage.md in
runs_out/qa/<today>/. `--propose rows.csv` writes the rows NOT in the queue in the class-C layout of docs/qa/customer-unmatched-classified-20261003.csv, ready for
scripts/add_customer_rows.py (which still decides what it will add). Exit code is 0 always: a coverage tool must never stop the Saturday job."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.stamp_given_ids import iso_of, norm_url                      # noqa: E402
from src.cfp_monitor import identity, qa_report                           # noqa: E402
from src.cfp_monitor.link_agreement import link_disagreement             # noqa: E402  (ACT-54: ONE rule, shared with match_customer_sheet)

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"
NOT_RESEARCHED = ROOT / "docs" / "operations" / "customer_not_researched.csv"
CLIENT_MARKET = {"arnica": "Cybersecurity", "utility-global": "Utility"}
CLIENT_SHEET = {"arnica": "arnica", "utility-global": "utility"}           # the `sheet` column of the classified CSV
PROPOSE_COLS = ["class", "sheet", "sheet_row", "conference", "customer_url", "customer_location", "customer_start", "customer_deadline", "our_event_id",
                "page_confirmed", "page_start_date", "evidence_url", "evidence_sentence", "note"]
DATE_TOLERANCE_DAYS = 30                                                    # a customer date and an event date further apart than this are different editions or places
LEDGER_COLS = ["event_name", "url", "client", "reason", "ruled_by", "ruled_on"]


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_ledger(path: Path) -> list[dict]:
    return read_csv(path) if Path(path).exists() else []


def build_queue(inputs: dict[str, list[dict]], up_to_canon: dict[str, str]) -> dict[str, dict]:
    """Per market: ids (canonical) and URLs of the live input rows, and the same of the DUP_OF rows (kept apart: a duplicate listing is not a queue entry)."""
    q = {}
    for market, rows in inputs.items():
        d = {"ids": {}, "urls": {}, "dup_ids": {}, "dup_urls": {}}
        for r in rows:
            ident = identity.to_canonical((r.get("EVENT_ID_CANON") or "").strip(), up_to_canon)
            url = norm_url(r.get("CONFERENCE URL", ""))
            dup = (r.get("DUP_OF") or "").strip()
            name = (r.get("CONFERENCE") or "").strip()
            ids, urls = ("dup_ids", "dup_urls") if dup else ("ids", "urls")
            if ident:
                d[ids].setdefault(ident, name)
            if url:
                d[urls].setdefault(url, []).append((name, iso_of(r.get("START DATE") or "")))
        q[market] = d
    return q


def days_apart(a: str, b: str) -> int | None:
    try:
        return abs((datetime.strptime(a, "%Y-%m-%d") - datetime.strptime(b, "%Y-%m-%d")).days)
    except ValueError:
        return None


def url_match(url: str, start: str, table: dict) -> str:
    """Name of an input row with this URL AND a matching date, else ''. The same website alone is NOT a pairing (Hack In The Box: the customer's Jakarta event hid behind our Phuket row on
    conference.hitb.org). When either side has no date the date cannot disprove the pairing, so the URL stands."""
    for name, their in table.get(url, []):
        gap = days_apart(start, their) if start and their else None
        if gap is None or gap <= DATE_TOLERANCE_DAYS:
            return name
    return ""


def stale_date(start: str, url: str) -> bool:
    """The customer's date has passed but their own URL names a LATER year (https://ecmlpkdd.org/2027/ with a 2026 date): the date was not updated for the next
    edition, so the event is not over and must not be silently excluded (a date is not proof of the right edition)."""
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", url or "")]
    return bool(years) and max(years) > int(start[:4])


def classify(row: dict, market: str, queue: dict, ledger: list[dict], today: str, up_to_canon: dict[str, str]) -> tuple[str, str, str]:
    """-> (verdict, how/why, input row name). verdict: IN_QUEUE | NOT_IN_QUEUE | EXCLUDED."""
    name = (row.get("their_name") or "").strip()
    if int(row.get("withdrawn_by_customer") or 0):
        return "EXCLUDED", "the customer removed this row from their sheet (withdrawn_by_customer)", ""
    start = iso_of(row.get("event_start_date") or "")
    if start and start < today and not stale_date(start, row.get("their_url") or ""):
        return "EXCLUDED", f"event is over: starts {start}, before {today}", ""
    url = norm_url(row.get("their_url") or "")
    for L in ledger:
        lc = (L.get("client") or "").strip().lower()
        if lc and lc not in (row["client_key"].lower(), CLIENT_SHEET[row["client_key"]]):
            continue
        if (L.get("event_name") or "").strip().lower() == name.lower() or (url and norm_url(L.get("url") or "") == url):
            return "EXCLUDED", f"operator's ledger (customer_not_researched.csv): {L.get('reason', '')} (ruled by {L.get('ruled_by', '?')} on {L.get('ruled_on', '?')})", ""
    q = queue[market]
    eid = identity.to_canonical((row.get("event_id") or "").strip(), up_to_canon)
    if eid and eid in q["ids"]:
        return "IN_QUEUE", "by event id", q["ids"][eid]
    hit = url_match(url, start, q["urls"]) if url else ""
    if hit:
        return "IN_QUEUE", "by URL and date" + (" (its id is not on that input row)" if eid else " (unlinked row)"), hit
    dup = q["dup_ids"].get(eid, "") or (url_match(url, start, q["dup_urls"]) if url else "")
    if dup:
        return "EXCLUDED", "the only input row it matches is marked DUP_OF", dup
    return "NOT_IN_QUEUE", "no input row has its event id or its URL", ""


def disagreement(row: dict, fact: dict | None, today: str) -> str:
    """Why the event a customer row is LINKED to is not the event the customer means ('' when it agrees or cannot be judged): its start date more than DATE_TOLERANCE_DAYS from the
    customer's date, or its city not named in the customer's location. Past events are included: a wrong link is wrong whatever the date."""
    if not fact or int(row.get("withdrawn_by_customer") or 0):
        return ""
    return link_disagreement(row.get("location") or "", iso_of(row.get("event_start_date") or ""), fact.get("city") or "", iso_of(fact.get("start_date") or ""), DATE_TOLERANCE_DAYS)


def check(rows: list[dict], inputs: dict[str, list[dict]], up_to_canon: dict[str, str], ledger: list[dict], today: str, facts: dict | None = None) -> dict:
    queue = build_queue(inputs, up_to_canon)
    out = {"today": today, "in_queue": [], "not_in_queue": [], "excluded": [], "disagree": []}
    for r in rows:
        market = CLIENT_MARKET.get(r["client_key"])
        if market is None or market not in queue:
            continue
        fact = (facts or {}).get(identity.to_canonical((r.get("event_id") or "").strip(), up_to_canon))
        bad = disagreement(r, fact, today)
        if bad:
            out["disagree"].append({"client": r["client_key"], "market": market, "name": r["their_name"], "customer_url": r.get("their_url") or "", "customer_start": iso_of(r.get("event_start_date") or ""),
                                    "customer_location": r.get("location") or "", "event_id": r.get("event_id") or "", "event_name": fact.get("name") or "", "event_start": iso_of(fact.get("start_date") or ""),
                                    "event_city": fact.get("city") or "", "event_url": fact.get("url") or "", "why": bad})
        verdict, why, matched = classify(r, market, queue, ledger, today, up_to_canon)
        item = {"client": r["client_key"], "market": market, "name": r["their_name"], "url": r.get("their_url") or "", "start": iso_of(r.get("event_start_date") or ""),
                "event_id": r.get("event_id") or "", "status": r.get("status") or "", "why": why, "input_row": matched, "_row": r}
        out[{"IN_QUEUE": "in_queue", "NOT_IN_QUEUE": "not_in_queue", "EXCLUDED": "excluded"}[verdict]].append(item)
    return out


def summary_lines(res: dict) -> list[str]:
    n, k = len(res["in_queue"]), len(res["not_in_queue"])
    j = len(res.get("disagree", []))
    lines = [f"COVERAGE: {n} of {n + k} customer rows ahead of {res['today']} are in the research queue; {k} are NOT; {j} linked rows disagree on date or place"]
    if j:
        lines.append("COVERAGE LINKED BUT DISAGREES: " + "; ".join(x["name"] for x in res["disagree"][:5]) + (f"; and {j - 5} more" if j > 5 else ""))
    if k:
        names = [x["name"] for x in res["not_in_queue"][:5]]
        lines.append("COVERAGE NOT IN QUEUE: " + "; ".join(names) + (f"; and {k - 5} more" if k > 5 else ""))
    return lines


def propose_rows(res: dict) -> list[dict]:
    """The NOT-in-queue rows in the class-C layout that add_customer_rows.py reads. page_confirmed is left blank: nobody has opened the event's page yet."""
    out = []
    for x in res["not_in_queue"]:
        r = x["_row"]
        out.append({"class": "C", "sheet": CLIENT_SHEET[x["client"]], "sheet_row": "", "conference": x["name"], "customer_url": x["url"], "customer_location": r.get("location") or "",
                    "customer_start": r.get("event_start_date") or "", "customer_deadline": r.get("their_deadline") or "", "our_event_id": x["event_id"], "page_confirmed": "",
                    "page_start_date": "", "evidence_url": "", "evidence_sentence": "", "note": "proposed by customer_coverage.py: " + x["why"]})
    return out


def markdown(res: dict, degraded: list[str]) -> str:
    L = ["# Customer coverage: is every customer row in the research queue?", "", f"Date: {res['today']}. Read-only check (scripts/customer_coverage.py).", ""]
    L += [f"- {s}" for s in summary_lines(res)] + [f"- Excluded, each with its reason: {len(res['excluded'])}"] + [f"- DEGRADED: {d}" for d in degraded] + [""]
    for title, key in (("NOT in the research queue", "not_in_queue"), ("Excluded (with reasons)", "excluded")):
        L += [f"## {title} ({len(res[key])})", ""]
        if res[key]:
            L += ["| client | event | start | status | why |", "|---|---|---|---|---|"]
            L += [f"| {x['client']} | {x['name']} | {x['start'] or '-'} | {x['status'] or '-'} | {x['why']} |" for x in res[key]]
        else:
            L += ["None."]
        L += [""]
    L += [f"## LINKED BUT DISAGREES ({len(res.get('disagree', []))})", "",
          "Customer rows whose linked event starts more than 30 days from the customer's date, or in another city. Report only: a person decides which side is right.", ""]
    if res.get("disagree"):
        L += ["| client | customer row | customer date | customer place | linked event | event date | event city | why |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {x['client']} | {x['name']} | {x['customer_start'] or '-'} | {x['customer_location'] or '-'} | {x['event_id']} | {x['event_start'] or '-'} | {x['event_city'] or '-'} | {x['why']} |"
              for x in res["disagree"]]
    else:
        L += ["None."]
    L += [""]
    by_how: dict[str, int] = {}
    for x in res["in_queue"]:
        by_how[x["why"]] = by_how.get(x["why"], 0) + 1
    L += [f"## In the queue ({len(res['in_queue'])})", ""] + [f"- {n} {how}" for how, n in sorted(by_how.items())] + [""]
    return "\n".join(L)


def run(db: Path, markets_dir: Path, ledger_path: Path, today: str) -> tuple[dict | None, list[str], str]:
    """(result or None, degraded notes, why it is unknown)."""
    if not Path(db).exists():
        return None, [], f"database not found ({db})"
    up_to_canon, roots = identity.seed_map(str(db))
    degraded = [] if up_to_canon else [f"the event-id seed map is empty (looked in {', '.join(map(str, roots)) or 'no market_sheets folder'}): ids are compared as spelled"]
    inputs = {}
    for market in CLIENT_MARKET.values():
        p = Path(markets_dir) / f"{market}_input.csv"
        if not p.exists():
            return None, degraded, f"input list not found ({p})"
        inputs[market] = read_csv(p)
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("select * from client_conferences")]
    finally:
        con.close()
    if not rows:
        return None, degraded, "client_conferences is empty"
    ledger = load_ledger(ledger_path)
    facts = {}
    try:
        fc = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
        fc.row_factory = sqlite3.Row
        facts = {r["event_id"]: dict(r) for r in fc.execute("select event_id, name, url, city, start_date from grounding_facts")}
        fc.close()
    except sqlite3.Error as e:
        degraded.append(f"grounding_facts could not be read ({e}): 'linked but disagrees' not checked")
    return check(rows, inputs, up_to_canon, ledger, today, facts), degraded, ""


def write_reports(res: dict, degraded: list[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = {k: ([{a: b for a, b in x.items() if a != "_row"} for x in v] if isinstance(v, list) else v) for k, v in res.items()}
    clean["summary"] = summary_lines(res)
    clean["degraded"] = degraded
    (out_dir / "coverage.json").write_text(json.dumps(clean, indent=1, ensure_ascii=True), encoding="utf-8")
    (out_dir / "coverage.md").write_text(markdown(res, degraded), encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--ledger", default=str(NOT_RESEARCHED))
    ap.add_argument("--out-dir", default="", help="default runs_out/qa/<today>")
    ap.add_argument("--propose", default="", help="write the rows NOT in the queue as a class-C CSV for add_customer_rows.py")
    a = ap.parse_args()
    try:
        res, degraded, why = run(Path(a.db), Path(a.markets_dir), Path(a.ledger), a.today)
        if res is None:
            print(f"COVERAGE: UNKNOWN - {why}")
            return 0
        for d in degraded:
            print(f"COVERAGE DEGRADED: {d}")
        for line in summary_lines(res):
            print(line)
        write_reports(res, degraded, Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today)
        if a.propose:
            rows = propose_rows(res)
            with open(a.propose, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=PROPOSE_COLS, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            print(f"COVERAGE: {len(rows)} proposed row(s) written to {a.propose}")
    except Exception as e:                                                  # a coverage tool must never stop the Saturday job
        print(f"COVERAGE: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
