"""What has the CUSTOMER already done with these rows? Ask before remediating any of them.

THE DAY THIS COST
On 2026-09-01 a full day of citation remediation ran row by row without once reading the client
layer. It was correct work on the wrong queue. Checked afterwards, 22 of the rows being
repaired had already been verified or acted on by Nicolia's team:

    World Future Energy Summit   status "Submitted"   - form already filed for the end client
    it-sa Expo & Congress        already submitted  [WRONG - see below]
    ADIPEC 2026                  status "Client Declined"
    ESF MENA                     status "Accepted", $12,500 sponsorship under consideration
    Horizons Asia 2027           status "Submitted"

Two of those are not merely wasted effort, they are contradictions we were about to ship. We
had ESF MENA marked `Closed` as a discontinued event while the customer holds an ACCEPTANCE to
it with money attached, and Horizons Asia queued for a discontinuation note while they have a
submission in. Downgrading a row to `Projected` tells a customer their own verified, acted-on
entry is unevidenced.

WHAT THIS CHANGES
The acceptance gate ranks work by rule violation. The customer ranks it by what they can still
act on. Those orders are close to inverted:

    highest value   "Info Needed", "Drafting Abstract" - live, deadline matters TODAY
    contradiction   our status disagrees with theirs - fix before anything else ships
    already moot    "Submitted", "Accepted", "Client Declined" - the deadline no longer bites
    lowest          not on any client sheet - industry coverage nobody is acting on

A gate failure on a row nobody is acting on is a tidy-up. A correct row whose deadline the
customer is drafting against is the product.

    python scripts/customer_context.py --names "H2 MEET" "ACT Expo"
    python scripts/customer_context.py --delivery <csv> --failures <gate-output.txt>
    python scripts/customer_context.py --all-acted

CORRECTION, 2026-09-16. The it-sa line above was this tool misreading its own input: Arnica's
SPEAKER & ABSTRACTS SUBMITTED cell for it-sa holds an organiser email address, and any non-blank
value was taken as "submitted". Their own note calls it exhibition-focused, not submitted. The
2026-09-01 figure of 22 rows already acted on was inflated by the same test on every row whose
cell held a contact. `clients.records_a_submission` now refuses an address as proof.

Read-only. It never writes: `status`, `status_details` and `NOTES` are the CUSTOMER's fields
under contract section 3, and nothing here may propose changing them.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.clients import (DONE_STATES as DONE, LIVE_STATES as LIVE,  # noqa: E402
                                     records_a_submission)

# Their pipeline states now come from ONE definition in clients.py. Until 2026-09-16 this file and
# sheet_reconcile.py each kept a copy, and they disagreed about "closed". This file never counted
# "closed" as done and still does not - that word's meaning is undecided (clients.UNDECIDED_STATES).


def _db() -> str:
    return os.path.join(os.environ["LOCALAPPDATA"], "CFP-Monitor", "cfp_monitor.db")


def _yes(v) -> bool:
    return str(v or "").strip().lower() not in ("", "0", "no", "false", "none", "n/a", "-")


def bucket(row: dict) -> str:
    """How much does this row's deadline still matter to the customer?"""
    st = str(row.get("status") or "").strip().lower()
    if _yes(row.get("withdrawn_by_customer")):
        return "MOOT"
    # Not _yes(): Arnica keeps organiser contact emails in this column, and an address is who
    # to write to, not proof anything was sent. Six rows were ranked MOOT on that until 2026-09-16.
    if records_a_submission(row.get("speaker_abstracts_submitted")):
        return "MOOT"
    if any(st.startswith(d) for d in DONE):
        return "MOOT"
    if any(st.startswith(x) for x in LIVE):
        return "LIVE"
    if _yes(row.get("submission_date_verified")):
        return "TRACKED"
    return "TRACKED"


def lookup(con, name: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT * FROM client_conferences WHERE their_name LIKE ? ORDER BY client_key",
        (f"%{name}%",))]


def describe(d: dict) -> str:
    bits = []
    st = (d.get("status") or "").strip()
    if st:
        bits.append(f"status={st}")
    if records_a_submission(d.get("speaker_abstracts_submitted")):
        bits.append("ALREADY SUBMITTED")
    # Only the word itself. "Needs Verification" is the OPPOSITE claim and was printed as
    # "date verified by their team" by the old any-non-blank test, until 2026-09-16.
    sdv = (d.get("submission_date_verified") or "").strip()
    if sdv.lower() == "verified":
        bits.append("date verified by their team")
    elif sdv:
        bits.append(f"date verification: {sdv}")
    if _yes(d.get("withdrawn_by_customer")):
        bits.append("WITHDRAWN by customer")
    td = (d.get("their_deadline") or "").strip()
    if td:
        bits.append(f"their deadline field: {td}")
    pr = (d.get("priority") or "").strip()
    if pr:
        bits.append(f"priority={pr}")
    return "; ".join(bits) or "on their sheet, nothing recorded"


def main() -> int:
    ap = argparse.ArgumentParser(description="Customer context for rows before remediating.")
    ap.add_argument("--names", nargs="*", default=[], help="conference name fragments")
    ap.add_argument("--all-acted", action="store_true",
                    help="every row the customer has submitted, accepted or declined")
    ap.add_argument("--db", default="")
    a = ap.parse_args()

    con = sqlite3.connect(a.db or _db())
    con.row_factory = sqlite3.Row

    if a.all_acted:
        rows = [dict(r) for r in con.execute("SELECT * FROM client_conferences")]
        acted = [r for r in rows if bucket(r) == "MOOT"]
        print(f"{len(acted)} of {len(rows)} client rows are already actioned - a deadline "
              f"correction on these has no consumer\n")
        for d in sorted(acted, key=lambda x: (x["client_key"], x["their_name"])):
            print(f"  [{d['client_key']}] {d['their_name'][:52]}")
            print(f"      {describe(d)}")
        return 0

    if not a.names:
        print("nothing to look up - pass --names or --all-acted")
        return 0

    order = {"LIVE": 0, "TRACKED": 1, "MOOT": 2, "UNTRACKED": 3}
    out = []
    for n in a.names:
        found = lookup(con, n)
        if not found:
            out.append(("UNTRACKED", n, None))
            continue
        for d in found:
            out.append((bucket(d), n, d))

    for b, n, d in sorted(out, key=lambda x: order[x[0]]):
        if d is None:
            print(f"  [UNTRACKED] {n[:48]}")
            print("      on no client sheet - industry coverage, nobody is acting on it")
            continue
        print(f"  [{b:<9}] {d['their_name'][:52]}  ({d['client_key']})")
        print(f"      {describe(d)}")
        det = (d.get("status_details") or "").strip()
        if det:
            print(f"      their note: {det[:150]}")
    print()
    print("LIVE      the deadline matters today - get this right first")
    print("TRACKED   on their sheet, not yet acted on")
    print("MOOT      already submitted, accepted or declined - a deadline fix has no consumer")
    print("UNTRACKED nobody is acting on it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
