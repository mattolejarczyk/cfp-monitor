"""'Awaiting research' rows: customer awards that no row of the page carries yet (ACT-70 follow-up; QA-REGISTER A67). Read-only.

    python scripts/awaiting_rows.py [--sheets-dir <dir>] [--page-csv <approved.csv>] [--on 2026-10-13]

WHY. Operator ruling 2026-10-13: the customer's sheets are the source of truth and EVERY award they track is shown. An award the customer added that is queued for the next research has no
research yet, so neither the approved file nor the Provisional rows carry it, and the customer could not see it on the page. This builds a page row for each such award from the customer's OWN sheet
only: name, market (arnica-awards -> Cybersecurity, utility-awards -> Utility), the customer's submission link, place, event date, and the customer's deadline ONLY when the cell is exactly one date;
otherwise the deadline stays blank and the customer's own words are shown in the detail panel as 'On your sheet: <text>'. Status: Needs Verification, or Closed when a parsed deadline has passed.
No confidence, no verdict, no dead-link flag: nothing about it is researched.

'ON THE PAGE' is decided the way the customer sheets are matched everywhere (customer_awards.name_key and url_key; a deep URL counts only when no other award of the customer's own sheet uses it and
only one page name carries it; never an upstream id) and only within the same market. Pure functions plus a thin reader.

Conferences: the same function would serve the Conference page given the conference sheets' snapshots (customer_sheets.json kind 'conference'; their columns differ: CONFERENCE, CONFERENCE URL,
EVENT START DATE) - see QA-REGISTER A67 for what it takes."""
from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import customer_awards as ca                                  # noqa: E402
from scripts.provisional_rows import clean_text                            # noqa: E402

FLAG = "_AWAITING"
SENTENCE = "On your sheet. Research for this award is scheduled this week; results will appear in next week's page."
MARKET_OF = {c: v["market"] for c, v in ca.CLIENTS.items()}
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)|(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


def single_iso_date(text: str) -> str:
    """The ISO date when the cell is exactly one date and nothing else; '' otherwise (a range, a phrase, two dates, a month name)."""
    t = (text or "").strip()
    m = DATE_RE.fullmatch(t)
    if not m:
        return ""
    try:
        d = date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m.group(3) else date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
    except ValueError:
        return ""
    return d.isoformat()


def _page_index(rows: list[dict]) -> dict:
    idx: dict = {}
    for r in rows:
        d = idx.setdefault((r.get("Market") or "").strip(), {"names": set(), "urls": {}})
        k = ca.name_key(r.get("CONFERENCE") or "")
        if k:
            d["names"].add(k)
        for col in ("SUBMISSION URL", "CFP_SUBMISSION_URL", "CONFERENCE URL", "MAIN_INFO_URL"):
            u = ca.url_key(r.get(col) or "")
            if u:
                d["urls"].setdefault(u, set()).add(k)
    return idx


def awaiting_candidates(page_rows: list[dict], sheets: dict[str, list[dict]], on: date) -> tuple[list[dict], list[dict]]:
    """-> (delivery rows tagged _AWAITING, report [{'name','market','deadline_cell','shown_deadline','status'}]). `sheets` = {client: customer_awards.sheet_rows(...)}."""
    idx = _page_index(page_rows)
    rows, rep, seen = [], [], set()
    for client, srows in sheets.items():
        market = MARKET_OF[client]
        d = idx.get(market, {"names": set(), "urls": {}})
        use: dict[str, set[str]] = {}
        for r in srows:
            u = ca.url_key(r["url"])
            if u:
                use.setdefault(u, set()).add(ca.name_key(r["name"]))
        for r in srows:
            k, u = ca.name_key(r["name"]), ca.url_key(r["url"])
            if not r["name"] or (market, k) in seen:
                continue
            if k and k in d["names"]:
                continue
            if u and len(use.get(u, set())) <= 1 and len(d["urls"].get(u, set())) == 1:
                continue
            seen.add((market, k))
            iso = single_iso_date(r["deadline"])
            status = "Closed" if iso and iso < on.isoformat() else "Needs Verification"
            details = f"On your sheet: {clean_text(r['deadline'])}" if r["deadline"] and not iso else ""
            ev = single_iso_date(r["event_date"])
            row = {"EVENT_ID": f"sheet-{client}-{r['sheet_row']}", "CONFERENCE": clean_text(r["name"]), "Market": market, "OPPORTUNITY_TYPE": "Awards", "STATUS": status,
                   "SUBMISSION DEADLINE": iso, "STATUS DETAILS": details, "SUBMISSION URL": r["url"], "CITY": clean_text(r["location"]), "START DATE": ev,
                   "CONFERENCE DATES": r["event_date"] if r["event_date"] and not ev else "", FLAG: "1"}
            rows.append(row)
            rep.append({"name": clean_text(r["name"]), "market": market, "deadline_cell": r["deadline"], "shown_deadline": iso, "status": status, "sheet_row": r["sheet_row"], "client": client})
    return rows, rep


def awaiting_rows(page_rows: list[dict], sheets_dir: Path, on: date) -> tuple[list[dict], list[dict], str]:
    """The reader: the newest snapshots of the two awards sheets under sheets_dir. -> (rows, report, note). A snapshot that cannot be read gives no rows and says why."""
    sheets = {}
    for client in ca.CLIENTS:
        p = ca.newest_sheet(Path(sheets_dir), client)
        if p is None:
            return [], [], f"no snapshot of the {client} sheet under {sheets_dir}"
        sheets[client] = ca.sheet_rows(p, client)
    rows, rep = awaiting_candidates(page_rows, sheets, on)
    return rows, rep, ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sheets-dir", default=str(ca.SNAPSHOTS))
    ap.add_argument("--page-csv", required=True, help="the rows already on the page (the approved awards file)")
    ap.add_argument("--on", default=date.today().isoformat())
    a = ap.parse_args()
    with open(a.page_csv, encoding="utf-8-sig", newline="") as fh:
        page = list(csv.DictReader(fh))
    rows, rep, note = awaiting_rows(page, Path(a.sheets_dir), date.fromisoformat(a.on))
    print(f"AWAITING: {len(rows)} customer award(s) are on no row of the page" + (f" - {note}" if note else ""))
    for e in rep:
        print(f"  {e['market']}: {e['name']} [{e['status']}] deadline cell={e['deadline_cell']!r} shown={e['shown_deadline'] or '(blank)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
