"""Two read-only sizing questions (2026-10-02). No network, no writes.

A. If verify_grounding could fall back to the saved page library when a plain fetch is refused (the Black Hat Asia case:
   HTTP 403 -> "the cited page could not be read" -> not_found), how many stored rows would change?
   For every row whose verify_detail says the cited page could not be read, look the cited URL up in the library and ask
   find_date(library text, stored deadline).

B. Of the customer-verified, dated rows with NO matching event of ours (the coverage gap), how many are still live?
   Live = the customer's own date is on or after the run date.
"""
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import verify  # noqa: E402

DB = Path.home() / "AppData/Local/CFP-Monitor/cfp_monitor.db"
TODAY = date(2026, 10, 2)


def main() -> None:
    con = sqlite3.connect(DB)
    lib = sqlite3.connect(ROOT / "page_library/page_library.db")
    pages = {u: t for u, t in lib.execute("select url, text from pages where text is not null and text != ''")}

    print("== A. rows whose cited page 'could not be read'")
    tot = in_lib = would = 0
    for table in ("grounding_facts", "award_grounding_facts"):
        q = (f"select event_id, name, deadline, deadline_evidence_url, verify_detail from {table} "
             "where verify_detail like '%could not be read%' and deadline != ''")
        for eid, name, dl, url, det in con.execute(q):
            tot += 1
            text = pages.get(url)
            if text is None:
                continue
            in_lib += 1
            try:
                ok = verify.find_date(text, date.fromisoformat(dl))
            except ValueError:
                continue
            would += ok
            print(f"   {'WOULD VERIFY' if ok else 'page in library, date not on it':32} {name[:48]} {dl}")
    print(f"   unreadable-page rows with a deadline: {tot}; cited page IS in the library: {in_lib}; date found there: {would}")

    print("\n== B. coverage gap: customer-verified dated rows with no matching event of ours")
    ours = {r[0] for t in ("grounding_facts", "award_grounding_facts") for r in con.execute(f"select event_id from {t}")}
    live, old = [], []
    for client, name, eid, theirs in con.execute(
            "select client_key, their_name, event_id, their_deadline from client_conferences "
            "where lower(trim(submission_date_verified))='verified' and trim(their_deadline)!='' "
            "and coalesce(withdrawn_by_customer,0)=0"):
        if eid in ours:
            continue
        try:
            d = datetime.strptime(theirs.strip(), "%m/%d/%Y").date()
        except ValueError:
            continue
        (live if d >= TODAY else old).append((d, client, name))
    print(f"   gap rows: {len(live) + len(old)}; customer date still ahead: {len(live)}; already passed: {len(old)}")
    for d, client, name in sorted(live):
        print(f"   LIVE  {d}  [{client}] {name[:60]}")


if __name__ == "__main__":
    main()
