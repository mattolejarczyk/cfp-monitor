"""Import an ACCEPTED awards delivery into `award_grounding_facts` and `award_markets`.

SEPARATE FROM CONFERENCES, ON PURPOSE AND BY INSTRUCTION
This writes to the award tables and nothing else. It does not read, write, join or migrate
`grounding_facts`, `conferences` or `conference_markets`, and it shares no code path with
`import_grounding.py`. What it does share is the RULES layer - `grounding.event_id`,
`storage.normalize_key` - because a rule copied is a rule that drifts, and the two id
namespaces are exactly where drift has cost the most.

    conferences  ->  grounding_facts   + conference_markets  (import_grounding.py)
    awards       ->  award_grounding_facts + award_markets   (this file)

THE GATE DECIDES
An awards delivery that is not ACCEPTED is never imported. This refuses to run without the
JSON that `accept_delivery.py` writes, refuses if that JSON is for a different file, and
refuses if any check in it failed. The runbook already says the gate decides; a standalone
importer that takes the operator's word for it is how that stops being true.

UPSTREAM'S EVENT_ID IS NOT OURS (contract 5.4)
The delivery's `EVENT_ID` column is upstream's key echoed back to us. We MINT our own from the
row's own fields and store theirs in `upstream_event_id` so the next patch can still be joined.
`identity.py` exists because this exact confusion has cost three separate incidents; the fix
there was one translation function, and the fix here is to never lose the other side of it.

Minting now is safe and is the only moment it is safe. R24/R25 freeze a key once minted, but
nothing has been imported yet, so no key can move. It is also why one delivery id reading
`...-2026-nan-awards` - a pandas artefact that reached an identifier - does not have to be
carried forever.

WHAT AN AWARD DOES NOT HAVE
Most of these rows have no venue and no event date. `city` is routinely empty and that is
correct, not missing: `event_id` falls back to `tbd`, and 2.6 prefers an honest blank to a
placeholder. Nothing here invents a location to make a key look tidier.

Reports by default. `--apply` backs the database up first.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.grounding import event_id as mint_event_id      # noqa: E402
from src.cfp_monitor.storage import normalize_key                    # noqa: E402

# delivery column -> award_grounding_facts column. Everything absent from this map is
# deliberately not imported: GATED_STATUS and ISSUES are derived downstream (R8a), and the
# customer's own columns are not ours to carry into our tables.
COLUMN_MAP = {
    "CONFERENCE":            "name",
    "CONFERENCE URL":        "url",
    "CITY":                  "city",
    "STATE_PROVINCE":        "state_province",
    "COUNTRY":               "country",
    "EDITION":               "edition",
    "SUBMISSION DEADLINE":   "deadline",
    "SUBMISSION URL":        "submission_url",
    "CFP MODEL TYPE":        "cfp_model",
    "STATUS":                "status",
    "OVERVIEW":              "overview",
    "CATEGORIES":            "categories",
    "COORDINATOR EMAIL":     "coordinator_email",
    "DEADLINE_QUOTE":        "deadline_quote",
    "IS_PROJECTED":          "is_projected",
    "SOURCE_AS_OF":          "source_as_of",
    "DEADLINE_EVIDENCE_URL": "deadline_evidence_url",
    "MAIN_INFO_URL":         "main_info_url",
    "ORGANIZER":             "organizer",
    "SPONSOR_REQUIRED":      "sponsor_required",
    "SPONSOR_URL":           "sponsor_url",
    "SPONSOR_COST":          "sponsor_cost",
    "SPONSOR_QUOTE":         "sponsor_quote",
    "SUBMISSION_OPENS":      "submission_opens",
    "ANNOUNCEMENT_DATE":     "announcement_date",
}

# Set by the verify pass, never by an import. Re-importing a row must not tell the system it
# has become unverified again - that is the mutation `check_invariants.py` exists to catch on
# the conference side.
PRESERVE_ON_REIMPORT = ("verify_state", "verify_detail")


def _g(row, key) -> str:
    return (row.get(key) or "").strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gate_says_accepted(gate_json: Path, delivery: Path) -> tuple[bool, str]:
    """The gate's own output is the only evidence this importer accepts."""
    try:
        data = json.loads(gate_json.read_text(encoding="utf-8"))
    except Exception as exc:                                         # noqa: BLE001
        return False, f"cannot read {gate_json.name}: {exc}"
    if delivery.name not in data:
        return False, (f"{gate_json.name} has results for {list(data)} - not for "
                       f"{delivery.name}. A gate run on a different file proves nothing.")
    checks = data[delivery.name]
    failed = [c["check"] for c in checks if not c.get("passed")]
    if failed:
        return False, f"the gate failed check(s) {failed} - an unaccepted delivery is never imported"
    return True, f"{len(checks)} of {len(checks)} checks passed"


def duplicate_names(seed: Path | None, known_names: set[str]) -> dict[str, str]:
    """CONFERENCE -> the row it duplicates, from the seed's DUP_OF column.

    THE LABELLING IS LOAD-BEARING HERE, not decorative. `grounding.slug` drops parenthetical
    asides, so `Fortress Cybersecurity Award (Business Intelligence Group)` and
    `Fortress Cybersecurity Award` mint one id - which is the same finding the duplicate pass
    reached from the other direction, and a second, independent reason to believe it.

    A collision the seed does NOT explain stays a refusal. That is the difference between a
    duplicate we have decided about and two rows that happen to collide, and only the first is
    safe to collapse.

    DUP_OF MEANS TWO DIFFERENT THINGS IN THIS COLUMN, and only one of them is an instruction
    to drop a row:

        DUP_OF = "Fortress Cybersecurity Award"   another row IN THIS DELIVERY. One award,
                                                  two names. Collapse onto the survivor.
        DUP_OF = "Utility Global:23"              a coordinate in the CUSTOMER's sheet. It
                                                  says the customer already lists this award.
                                                  It is a cross-reference, NOT a deletion.

    Eight rows carried the second kind before the duplicate pass ever ran. Treating them as the
    first kind drops them from the database - and one of them, Goldman Environmental Prize, is
    a row whose citation we withdrew by agreement three hours ago. So a name is returned only
    when it names something in `known_names`; everything else is left alone.
    """
    if seed is None:
        return {}
    with open(seed, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = {}
    for r in rows:
        name, target = (r.get("CONFERENCE") or "").strip(), (r.get("DUP_OF") or "").strip()
        if target and target in known_names:
            out[name] = target
    return out


def plan(delivery: Path, db: str,
         seed: Path | None = None) -> tuple[list[dict], list[str], list[str]]:
    with open(delivery, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    dups = duplicate_names(seed, {(_g(r, 'CONFERENCE')) for r in rows})

    problems, planned, skipped, seen = [], [], [], {}
    for r in rows:
        name = _g(r, "CONFERENCE")
        opportunity = _g(r, "OPPORTUNITY_TYPE")
        if opportunity != "Awards":
            # Not a defect and not ours: the awards market file carries a few rows typed as
            # conference opportunities. Excluded rather than coerced - writing a Speaking row
            # into the award tables is exactly the mixing the two pipelines are kept apart to
            # prevent - and listed, because a silent exclusion is indistinguishable from a bug.
            skipped.append(f"{name[:46]}: OPPORTUNITY_TYPE={opportunity!r}, not an award")
            continue
        if name in dups:
            skipped.append(f"{name[:46]}: labelled DUP_OF {dups[name][:40]!r} in the seed")
            continue
        canonical = mint_event_id(name, _g(r, "EDITION"), _g(r, "CITY"),
                                  _g(r, "LOCATION"), opportunity)
        if canonical in seen:
            problems.append(f"two rows mint the same id {canonical!r}: "
                            f"{seen[canonical][:40]!r} and {name[:40]!r}. If they are the "
                            f"same award, label one DUP_OF in the seed and re-run")
            continue
        seen[canonical] = name

        rec = {"event_id": canonical,
               "upstream_event_id": _g(r, "EVENT_ID"),
               "conference_key": normalize_key(_g(r, "MAIN_INFO_URL")
                                               or _g(r, "CONFERENCE URL")),
               "imported_at": _now()}
        for src, dest in COLUMN_MAP.items():
            rec[dest] = _g(r, src)
        rec["_market"] = _g(r, "Market")
        planned.append(rec)

    con = sqlite3.connect(db)
    existing = {x[0] for x in con.execute("select event_id from award_grounding_facts")}
    con.close()
    for rec in planned:
        rec["_new"] = rec["event_id"] not in existing
    return planned, problems, skipped


def apply(db: str, planned: list[dict], source_list: str) -> tuple[int, int, int]:
    con = sqlite3.connect(db)
    cols = {c[1] for c in con.execute("pragma table_info(award_grounding_facts)")}
    if "upstream_event_id" not in cols:
        # Additive, on an empty table, and required by 5.4: without somewhere to keep
        # upstream's key, the next patch keyed on it has nothing to join to and we would be
        # re-deriving the crossing that identity.py exists to stop being re-derived.
        con.execute("alter table award_grounding_facts add column upstream_event_id TEXT")
        print("  added column upstream_event_id")
        cols.add("upstream_event_id")

    inserted = updated = 0
    for rec in planned:
        payload = {k: v for k, v in rec.items() if k in cols and not k.startswith("_")}
        if rec["_new"]:
            names = ", ".join(payload)
            marks = ", ".join("?" for _ in payload)
            con.execute(f"insert into award_grounding_facts ({names}) values ({marks})",
                        list(payload.values()))
            inserted += 1
        else:
            sets = ", ".join(f"{k} = ?" for k in payload if k != "event_id")
            vals = [v for k, v in payload.items() if k != "event_id"]
            con.execute(f"update award_grounding_facts set {sets} where event_id = ?",
                        [*vals, rec["event_id"]])
            updated += 1

    # award_key is the canonical EVENT_ID, DELIBERATELY unlike conference_markets, which keys
    # membership by host. One host runs several award programmes with different deadlines and
    # different audiences - cloud-awards.com runs Security, SaaS, Cloud Computing and AI - so a
    # host-keyed membership cannot say which programme belongs to which market. The delivery
    # states Market per ROW, and the row is the programme.
    members = 0
    for rec in planned:
        if not rec["_market"]:
            continue
        cur = con.execute("insert or ignore into award_markets (award_key, market, "
                          "source_list, first_seen) values (?, ?, ?, ?)",
                          (rec["event_id"], rec["_market"], source_list, _now()))
        members += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    con.commit()
    con.close()
    return inserted, updated, members


def reconcile(db: str, planned: list[dict]) -> list[str]:
    """A mutation needs a reconciliation. Every planned row present, and nothing invented."""
    con = sqlite3.connect(db)
    have = {x[0] for x in con.execute("select event_id from award_grounding_facts")}
    markets = {x[0] for x in con.execute("select award_key from award_markets")}
    con.close()
    want = {r["event_id"] for r in planned}
    faults = []
    missing = sorted(want - have)
    if missing:
        faults.append(f"{len(missing)} delivered row(s) are NOT in the database: {missing[:5]}")
    orphan = sorted(markets - have)
    if orphan:
        faults.append(f"{len(orphan)} award_markets row(s) point at no award: {orphan[:5]}")
    expected = {r["event_id"] for r in planned if r["_market"]}
    lost = sorted(expected - markets)
    if lost:
        faults.append(f"{len(lost)} row(s) carry a Market but have no membership: {lost[:5]}")
    return faults


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("delivery")
    ap.add_argument("--db", required=True)
    ap.add_argument("--gate-json", required=True,
                    help="the JSON accept_delivery.py wrote for THIS delivery")
    ap.add_argument("--seed", help="the awards seed CSV, read for its DUP_OF column")
    ap.add_argument("--source-list", default="awards-batch-1")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    delivery, gate_json = Path(a.delivery), Path(a.gate_json)
    ok, why = gate_says_accepted(gate_json, delivery)
    print(f"gate     {gate_json.name}: {why}")
    if not ok:
        print("\nREFUSED - the gate decides, and it has not accepted this file.")
        return 2

    planned, problems, skipped = plan(delivery, a.db,
                                     Path(a.seed) if a.seed else None)
    if problems:
        print("\nREFUSED\n")
        for p in problems:
            print(f"  - {p}")
        return 2

    if skipped:
        print(f"\nEXCLUDED ({len(skipped)}), and each one deliberately:")
        for line in skipped:
            print(f"  - {line}")
        print()
    new = [r for r in planned if r["_new"]]
    upd = [r for r in planned if not r["_new"]]
    renamed = [r for r in planned if r["event_id"] != r["upstream_event_id"]]
    print(f"delivery {delivery.name}: {len(planned)} awards row(s)")
    print(f"         {len(new)} new, {len(upd)} already present")
    print(f"         {len(renamed)} row(s) get a canonical id differing from upstream's (5.4)")
    for r in renamed[:6]:
        print(f"           {r['upstream_event_id']}")
        print(f"        -> {r['event_id']}")
    if len(renamed) > 6:
        print(f"           ... and {len(renamed) - 6} more")

    by_market: dict[str, int] = {}
    for r in planned:
        by_market[r["_market"] or "(none)"] = by_market.get(r["_market"] or "(none)", 0) + 1
    print("         markets: " + ", ".join(f"{k} {v}" for k, v in sorted(by_market.items())))

    if not a.apply:
        print("\nreport only. Re-run with --apply to write.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{a.db}.backup-pre-awardimport-{stamp}.db"
    shutil.copy(a.db, backup)
    print(f"\nbackup   {Path(backup).name}")

    inserted, updated, _members = apply(a.db, planned, a.source_list)
    print(f"written  {inserted} inserted, {updated} updated")

    faults = reconcile(a.db, planned)
    if faults:
        print("\nRECONCILIATION FAILED - restore from the backup above:")
        for f in faults:
            print(f"  - {f}")
        return 3
    print("reconciled: every delivered row present, every membership accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
