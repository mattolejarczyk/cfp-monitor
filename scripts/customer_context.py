"""What has the CUSTOMER already done with these rows? Ask before remediating any of them.

THE DAY THIS COST
On 2026-09-01 a full day of citation remediation ran row by row without once reading the client
layer. It was correct work on the wrong queue. Checked afterwards, 22 of the rows being
repaired had already been verified or acted on by Nicolia's team:

    World Future Energy Summit   status "Submitted"   - form already filed for the end client
    it-sa Expo & Congress        already submitted
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

# Their pipeline states, ranked by how much a deadline still matters to them.
LIVE = ("info needed", "drafting abstract", "in progress", "reviewing", "interested")
DONE = ("submitted", "accepted", "declined", "client declined", "rejected", "withdrawn",
        "not pursuing", "passed")


def _db() -> str:
    return os.path.join(os.environ["LOCALAPPDATA"], "CFP-Monitor", "cfp_monitor.db")


def _yes(v) -> bool:
    return str(v or "").strip().lower() not in ("", "0", "no", "false", "none", "n/a", "-")


def bucket(row: dict) -> str:
    """How much does this row's deadline still matter to the customer?"""
    st = str(row.get("status") or "").strip().lower()
    if _yes(row.get("withdrawn_by_customer")):
        return "MOOT"
    if _yes(row.get("speaker_abstracts_submitted")):
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
    if _yes(d.get("speaker_abstracts_submitted")):
        bits.append("ALREADY SUBMITTED")
    if _yes(d.get("submission_date_verified")):
        bits.append("date verified by their team")
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
