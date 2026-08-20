"""Bring the delivery spreadsheet up to date from the database. MERGE, never regenerate.

WHY THIS IS A MERGE AND NOT AN EXPORT
The obvious tool here is "write the CSV out of the database". It would be wrong. The delivery
carries 38 columns and the database is the authority for 25 of them. The other 13 - FORMAT,
TRACK, PRIORITY, OPPORTUNITY_TYPE, GROUNDING_CONFIDENCE, LIFECYCLE_EVIDENCE_URL,
LIFECYCLE_QUOTE, VENUE_EVIDENCE_URL and friends - are upstream's research fields. We never
store them, so a regenerated file would blank a third of the customer's data while looking
complete. That is the same failure as a page built without --checks: a missing input reading
as a finding.

So the delivered CSV stays the base. Every column and every row survives untouched unless the
database owns that field and holds something different.

WHAT PROBLEM IT SOLVES
The HTML page the customer reads is built from the CSV. Corrections land in the database. Between
2026-08-07 and 2026-08-11 those diverged: GreenBiz was corrected by eight months, two rows were
retired, 25 citations were verified - and the page would have shown none of it, because nothing
carried the database back to the file.

WHAT IT DELIBERATELY DOES NOT TOUCH
  NOTES, STATUS DETAILS   customer-facing prose. An instruction to "fold X into STATUS DETAILS"
                          nearly destroyed 93 rows of it once; it is not ours to rewrite.
  SUBMISSION URL          upstream's field under contract section 3, even when we have found a
                          better one. The 15 replacements from 2026-08-09 stay in the hand-back
                          until upstream adopts them - see --report-only-gaps.
  anything with no DB source

Reports by default. Writes only with --apply.

    python scripts/refresh_delivery.py -i ALL_MARKETS_AUDITED_<date>.csv \
        --db <live.db> -o ALL_MARKETS_REFRESHED_<date>.csv [--apply]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.verify import _parse_date          # noqa: E402

# delivery column -> grounding_facts column. ONLY fields our pipeline is the authority for.
# Adding a row here means claiming we own that field; do not add one without checking the
# contract first.
OWNED = {
    "SUBMISSION DEADLINE":   "deadline",
    "DEADLINE_QUOTE":        "deadline_quote",
    "DEADLINE_EVIDENCE_URL": "deadline_evidence_url",
    "IS_PROJECTED":          "is_projected",
    "SOURCE_AS_OF":          "source_as_of",
    "CFP MODEL TYPE":        "cfp_model",
    "MAIN_INFO_URL":         "main_info_url",
    "CITY":                  "city",
    "STATE_PROVINCE":        "state_province",
    "COUNTRY":               "country",
    "EDITION":               "edition",
    # v1.5 (R20a). SPONSOR_QUOTE is the one sponsor column WE produce - upstream ships it
    # blank by agreement. Without it here, a quote we extract sits in the database and
    # never reaches the delivery, so it never reaches the customer page either. The other
    # four sponsor columns are upstream's and pass through untouched.
    "SPONSOR_QUOTE":         "sponsor_quote",
}

# Never written, and each for its own reason - see the module docstring.
PROTECTED = {"NOTES", "STATUS DETAILS", "SUBMISSION URL", "CFP_SUBMISSION_URL"}


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


# EVERY WAY WE DELIBERATELY EMPTY A FIELD, IN ONE PLACE.
# A blank in the database normally means "never populated" and must not overwrite customer
# data. The exceptions are the paths where we cleared it ON PURPOSE, and each writes a marker
# into verify_detail. This test has now been too narrow twice: first it checked
# cfp_model == "Not Announced", which missed a call that ran and CLOSED; then it checked for
# "[retired]" alone, which missed R1 withdrawals and left four dead 404 links in the delivery
# while the database said they were gone. A literal in the condition is how that keeps
# happening, so the markers live here and every writer must add its own.
CLEAR_MARKERS = ("[retired]", "[R1 withdrawal]")

# Columns a deliberate clear may empty. Everything else keeps the customer value even when
# the database is blank, because for those a blank means "never populated".
CLEARABLE = {"SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE"}


def _is_deliberate_clear(verify_detail: str) -> bool:
    return _norm(verify_detail).startswith(CLEAR_MARKERS)


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge database corrections into the delivery CSV.")
    ap.add_argument("-i", "--input", required=True, help="the delivered CSV (the base)")
    ap.add_argument("--db", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only-verified", action="store_true",
                    help="carry a SUBMISSION DEADLINE change only when the row's verify_state "
                         "is 'verified'. Everything else in the database rides along otherwise "
                         "- including upstream claims nothing ever checked.")
    ap.add_argument("--overrides",
                    help="CSV of per-ROW corrections the database cannot express, keyed on "
                         "EVENT_ID + TRACK. For events running several calls under one id: the "
                         "database holds one row per EVENT_ID, so a second call has nowhere to "
                         "live. Columns: EVENT_ID, TRACK, REASON, then any delivery column to "
                         "set. A QUOTE is verified against its URL before being written.")
    ap.add_argument("--exclude", default="",
                    help="comma-separated text; any row whose CONFERENCE contains one of these "
                         "is left completely untouched")
    a = ap.parse_args()
    excludes = [x.strip().lower() for x in a.exclude.split(",") if x.strip()]

    with open(a.input, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames or [])
        rows = list(reader)
    if not cols:
        print("ERROR: input has no header")
        return 2

    # CHECK WE CAN WRITE BEFORE DOING ANY WORK. Excel holds an exclusive lock on an open
    # workbook, so --apply did everything, copied a backup, then died on the final write - three
    # times, leaving three identical stray .bak files and an unchanged output. Worse, piping the
    # run through grep hid the traceback and the report looked like a success.
    if a.apply:
        out_p = Path(a.output)
        try:
            if out_p.exists():
                with open(out_p, "a", encoding="utf-8"):
                    pass
            else:
                out_p.parent.mkdir(parents=True, exist_ok=True)
                out_p.touch()
                out_p.unlink()
        except PermissionError:
            print(f"REFUSING: cannot write {out_p}\n"
                  "  It is open in another program - Excel takes an exclusive lock.\n"
                  "  Close it and run again. Nothing has been changed.")
            return 2

    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    facts = {r["event_id"]: r for r in con.execute("select * from grounding_facts")}
    if not facts:
        print("REFUSING: grounding_facts is empty. Point --db at the live database.")
        return 2

    # THE DELIVERY CARRIES UPSTREAM'S EVENT_ID, NOT OURS (contract 5.4). A direct lookup matches
    # nothing - the first run of this reported 406 unmatched rows and zero changes. Reuse the
    # one mapping implementation rather than writing a third; it also resolves the seeds beside
    # the database, which is where they live.
    import importlib.util as _ilu
    _s = _ilu.spec_from_file_location("_ar", Path(__file__).resolve().parent / "apply_resolutions.py")
    _ar = _ilu.module_from_spec(_s)
    _s.loader.exec_module(_ar)

    class _S:
        path = a.db
    up_to_canon, seed_roots = _ar._seed_map(_S())
    if not up_to_canon:
        print(f"REFUSING: no EVENT_ID map. Looked for market_sheets in "
              f"{[str(p) for p in seed_roots] or 'nowhere'}.\n"
              "Without it every row fails to match and the refresh reports no changes -\n"
              "a setup problem that looks exactly like 'nothing to do'.")
        return 2
    print(f"id map: {len(up_to_canon)} upstream ids -> canonical\n")

    print(f"base  : {a.input}")
    print(f"        {len(rows)} rows, {len(cols)} columns")
    print(f"db    : {a.db}")
    print(f"        {len(facts)} rows\n")

    # Columns the DB cannot supply. Named out loud every run, so nobody assumes a refreshed
    # file is fully database-backed.
    unbacked = [c for c in cols if c not in OWNED and c not in PROTECTED]
    print(f"carried through from the delivery untouched ({len(unbacked)} columns):")
    print("   " + ", ".join(unbacked) + "\n")

    changes: list[tuple[str, str, str, str, str]] = []
    unmatched: list[str] = []
    rejected_values: list[tuple[str, str]] = []
    withheld: list[tuple[str, str, str, str]] = []
    held: list[str] = []
    split_reported: list[tuple[str, str, list]] = []
    today = date.today()
    stale_status = 0

    # ONE EVENT_ID, TWO DIFFERENT CALLS - DO NOT GUESS WHICH THE DATABASE MEANS.
    # MD&M West 2027 appears twice under one EVENT_ID: the SPE MiniTec track (deadline
    # 2026-09-01, cited to spemedicalplastics.org, still open) and the MedTech Conference track
    # (2026-07-24, closed). The database holds one row per EVENT_ID, so it physically cannot
    # represent both - and writing its single value into both rows would have destroyed a live
    # opportunity while looking like a tidy correction. R10 says identity is call-level; where
    # the delivery disagrees with itself, the honest move is to touch neither row and say so.
    split: dict[str, set] = {}
    for r in rows:
        raw = _norm(r.get("EVENT_ID"))
        split.setdefault(raw, set()).add(_norm(r.get("SUBMISSION DEADLINE")))
    contested = {k for k, v in split.items() if len(v) > 1}

    for r in rows:
        raw = _norm(r.get("EVENT_ID"))
        if raw in contested:
            if raw not in [c[0] for c in split_reported]:
                split_reported.append((raw, _norm(r.get("CONFERENCE")), sorted(split[raw])))
            continue
        f = facts.get(up_to_canon.get(raw, raw))
        if not f:
            unmatched.append(r.get("CONFERENCE", "?"))
            continue
        name = _norm(r.get("CONFERENCE"))[:40]
        if any(x in name.lower() for x in excludes):
            held.append(name)
            continue
        for col, dbcol in OWNED.items():
            if col not in r:
                continue
            old, new = _norm(r[col]), _norm(f[dbcol])
            # A BLANK IN THE DATABASE IS ONLY MEANINGFUL WHEN IT WAS MADE ON PURPOSE. For the
            # deadline that is the retire path, which also sets cfp_model = Not Announced; for
            # anything else an empty column is far more likely to mean "never populated" than
            # "cleared", and clearing the customer's data on that basis is how a refresh
            # becomes a deletion.
            # An intentional clear is marked as one. Testing cfp_model == "Not Announced" was
            # too narrow: a call that ran and CLOSED is retired with model "Fixed Deadline" and
            # status Closed, so its blank was silently skipped and the disproven date stayed in
            # the customer's file. The retirement marker in verify_detail is the explicit
            # signal; anything else empty still means "never populated", not "cleared".
            # WHICH FIELDS A DELIBERATE CLEAR IS ALLOWED TO EMPTY. Scoping this to
            # SUBMISSION DEADLINE alone was the third miss in the same place: --retire empties
            # the DEADLINE, but an R1 withdrawal empties the CITATION and keeps the date, so
            # its blanks were skipped and six rows kept a dead 404 link in the customer file
            # while the database showed none. The marker says the clear was intentional; this
            # says which columns that licence covers.
            retired = _is_deliberate_clear(f["verify_detail"])
            if not new and old:
                intentional = retired or (col == "SUBMISSION DEADLINE"
                                          and _norm(f["cfp_model"]) == "Not Announced")
                if not (col in CLEARABLE and intentional):
                    continue
            # A DATE COLUMN TAKES A DATE OR NOTHING. Our own database holds
            # "Not yet published for 2027" in SUBMISSION DEADLINE for CS MANTECH - the same
            # prose-in-a-date-field we rejected from upstream, sitting on our side. Writing it
            # into the delivery would put a sentence in front of the customer and break every
            # downstream date comparison. Report it, refuse to propagate it.
            if col == "SUBMISSION DEADLINE" and new and not _parse_date(new):
                rejected_values.append((name, new))
                continue
            # An unverified deadline is upstream's claim sitting in our database, not our
            # finding. --only-verified stops it riding into the delivery on the strength of
            # "the database is the source of truth".
            # A RETIREMENT IS A DECISION, NOT A FAILED VERIFICATION. --retire deliberately
            # blanks a deadline neither side can source and sets Not Announced; its
            # verify_state is 'not_found' by design. Withholding it here would silently keep an
            # unsupported date in the customer's file - the exact thing the retirement removed.
            if (a.only_verified and col == "SUBMISSION DEADLINE" and not retired
                    and _norm(f["verify_state"]) != "verified" and old != new):
                withheld.append((name, old, new, _norm(f["verify_state"])))
                continue
            if old != new:
                changes.append((name, col, old, new, _norm(f["verify_state"])))
                if a.apply:
                    r[col] = new
        # A status that contradicts its own date, reported not fixed - STATUS is upstream's.
        d = _parse_date(_norm(r.get("SUBMISSION DEADLINE")))
        if d and d < today and _norm(r.get("STATUS")) in ("Open", "Upcoming"):
            stale_status += 1

    if unmatched:
        print(f"!! {len(unmatched)} delivery row(s) have no database row - left untouched:")
        for n in unmatched[:8]:
            print(f"     {n[:60]}")
        print()

    by_col: dict[str, int] = {}
    for _n, c, _o, _w, _st in changes:
        by_col[c] = by_col.get(c, 0) + 1
    print(f"{len(changes)} field change(s) across {len({c[0] for c in changes})} row(s):")
    for c, n in sorted(by_col.items(), key=lambda x: -x[1]):
        print(f"   {n:>4}  {c}")
    print()
    for name, col, old, new, st in changes:
        flag = "" if st == "verified" else f"   [{st or 'unknown'}]"
        print(f"  {name:<40} {col}{flag}")
        print(f"      {old[:88] or '(blank)'}")
        print(f"   -> {new[:88] or '(blank)'}")

    # A DEADLINE CHANGE THAT NOTHING VERIFIED IS NOT OUR FINDING - it is upstream's unchecked
    # claim, sitting in our database because we imported it. Pushing it into the delivery under
    # cover of "the database is the source of truth" would launder an unverified value into a
    # customer-facing correction. MD&M West is the case that prompted this: 2026-09-01, verdict
    # unreadable, cited to a co-located society's page we could not read.
    risky = [(n, o, w, st) for n, c, o, w, st in changes
             if c == "SUBMISSION DEADLINE" and st != "verified"]
    if risky:
        print("\n" + "!" * 88)
        print(f"{len(risky)} DEADLINE change(s) are NOT backed by a verified reading. "
              f"Check each before applying:")
        for n, o, w, st in risky:
            print(f"   {n[:42]:<42} {o or '(blank)':<14} -> {w or '(blank)':<14} [{st}]")
        print(f"{'!'*88}")

    # ---- per-row overrides, applied AFTER the database merge -------------------------------
    # These exist for rows the split guard above deliberately refuses to touch. MD&M West 2027
    # runs two calls under one EVENT_ID - the MedTech Conference call (closed 24 Jul) and the
    # SPE MiniTec track (DEADLINE September 1, 2026, live, evidenced at mpd.4spe.org). The
    # database can hold one of those. The delivery holds both, and this is how the second one
    # gets a working citation without pretending the database knows about it.
    applied_over: list[tuple[str, str, str, str]] = []
    if a.overrides:
        with open(a.overrides, encoding="utf-8-sig", newline="") as fh:
            over = list(csv.DictReader(fh))
        for o in over:
            eid, track = _norm(o.get("EVENT_ID")), _norm(o.get("TRACK"))
            reason = _norm(o.get("REASON"))
            if not reason:
                print(f"SKIP override for {eid[:40]} - no REASON given")
                continue
            targets = [r for r in rows if _norm(r.get("EVENT_ID")) == eid
                       and (not track or _norm(r.get("TRACK")) == track)]
            if not targets:
                print(f"SKIP override - no row matches EVENT_ID={eid[:44]} TRACK={track!r}")
                continue
            # Blank in the CSV means "not specified here"; the sentinel means "clear this".
            # Without it there was no way to remove a value - ABLC kept a DEADLINE_EVIDENCE_URL
            # pointing at a domain that no longer exists, citing a deadline that is itself
            # blank. A citation to nothing, for nothing.
            fields = {k: ("" if _norm(v) == "__CLEAR__" else v) for k, v in o.items()
                      if k not in ("EVENT_ID", "TRACK", "REASON")
                      and (_norm(v) or _norm(v) == "__CLEAR__")}
            # Same bar as everywhere else: a quote must be on the page we cite for it.
            q = _norm(fields.get("DEADLINE_QUOTE"))
            u = _norm(fields.get("DEADLINE_EVIDENCE_URL"))
            if q:
                from src.cfp_monitor.verify import fetch_text, normalize_text
                text, _n = fetch_text(u)
                if not text:
                    try:
                        import asyncio as _aio
                        _sp = _ilu.spec_from_file_location(
                            "_ae2", Path(__file__).resolve().parent / "audit_evidence.py")
                        _aem = _ilu.module_from_spec(_sp)
                        _sp.loader.exec_module(_aem)
                        text = _aio.run(_aem.escalate([u])).get(u, ("", ""))[0]
                    except Exception:
                        text = ""
                if normalize_text(q) not in normalize_text(text):
                    print(f"REJECT override for {eid[:36]} - quote is NOT on {u[:44]}")
                    continue
            for r in targets:
                for k, v in fields.items():
                    if k in r and _norm(r[k]) != _norm(v):
                        applied_over.append((_norm(r.get("CONFERENCE"))[:38], k,
                                             _norm(r[k]), _norm(v)))
                        if a.apply:
                            r[k] = _norm(v)

    if applied_over:
        print(f"\n{len(applied_over)} per-row override(s) applied "
              f"(rows the database cannot represent):")
        for n, k, o, w in applied_over:
            print(f"     {n:<38} {k}")
            print(f"        {o[:80] or '(blank)'}")
            print(f"     -> {w[:80] or '(blank)'}")

    if split_reported:
        print(f"\n{len(split_reported)} EVENT_ID(s) carry MORE THAN ONE deadline in the "
              f"delivery - left completely untouched:")
        for eid, name, vals in split_reported:
            print(f"     {name[:44]:<44} {' | '.join(v or '(blank)' for v in vals)}")
            print(f"        {eid}")
        print("   The database holds one row per EVENT_ID and cannot say which call it means.")
        print("   These are separate calls sharing an id (R10) - upstream needs to split them.")

    if held:
        print(f"\n{len(held)} row(s) held out by --exclude, untouched:")
        for n in held:
            print(f"     {n}")

    if withheld:
        print(f"\n{len(withheld)} deadline change(s) WITHHELD by --only-verified:")
        for n, o, w, st in withheld:
            print(f"     {n[:42]:<42} {o or '(blank)':<14} -> {w or '(blank)':<14} [{st}]")
        print("   Verify these, or fix them in the database. They will keep being offered.")

    if rejected_values:
        print(f"\n!! {len(rejected_values)} value(s) in the DATABASE are not valid dates "
              f"and were NOT written:")
        for n, v in rejected_values:
            print(f"     {n[:44]:<44} SUBMISSION DEADLINE = {v!r}")
        print("   Fix these in the database - a date column must hold a date or nothing.")

    if stale_status:
        print(f"\nNOTE: {stale_status} row(s) still say Open/Upcoming with a passed deadline. "
              f"STATUS is upstream's field so it is NOT rewritten here - the HTML page derives "
              f"Closed from the date at render time instead.")

    if not a.apply:
        print(f"\nreport only - re-run with --apply to write {a.output}")
        return 0

    out = Path(a.output)
    if out.exists():
        bak = out.with_suffix(f".bak-{datetime.now():%Y%m%d-%H%M%S}.csv")
        shutil.copy2(out, bak)
        print(f"\nexisting output backed up to {bak.name}")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # RECONCILE. A merge that loses a row or a column has failed even if every change was right.
    with open(out, encoding="utf-8-sig", newline="") as fh:
        chk = csv.DictReader(fh)
        wrote_cols, wrote_rows = list(chk.fieldnames or []), list(chk)
    assert wrote_cols == cols, "column set changed - refusing to trust this file"
    assert len(wrote_rows) == len(rows), "row count changed - refusing to trust this file"
    print(f"wrote {out}  ({len(wrote_rows)} rows, {len(wrote_cols)} columns - both reconcile)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
