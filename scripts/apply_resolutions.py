"""Apply upstream defend-or-correct resolutions to the discovery layer.

    python scripts/apply_resolutions.py --db cfp_monitor.db [--apply]
    python scripts/apply_resolutions.py --db cfp_monitor.db --citations <csv> [--apply]

Three resolution types, each landing differently:
  CORRECTED  upstream accepted our evidence -> take the corrected deadline, mark verified
             (our own crawl already read that date off the page, so it is evidence-backed).
  DEFENDED   upstream produced a verbatim quote + deep link -> keep THEIR value and store the
             evidence, so the next pass can confirm it automatically instead of re-arguing.
  UNCERTAIN  neither side can establish it -> blank the deadline, Not Announced. Better an
             admitted gap than a confident wrong date.

--citations MODE: THE MERGE GUARD
Added 2026-08-11 for the citation-repair round. Upstream returns a CSV of replacement
citations; this decides which are safe to take.

Four rules, and every one of them exists because the alternative loses data:

 1. A BLANK NEVER OVERWRITES A POPULATED FIELD. When resolution fails, upstream's script emits
    an empty DEADLINE_EVIDENCE_URL and DEADLINE_QUOTE. All 93 rows in that round already had
    both populated - IROS carried "Paper submission deadline: March 2, 2026". Merging blindly
    would destroy good evidence to fix a citation problem. Contract 2.1: absence is never
    disproof.
 2. A NEW CITATION MUST SURVIVE OUR OWN AUDIT. We fetch it, and the quote must appear on that
    page. Upstream marking a row verified is a claim, not a verification - their check passes
    a URL whose DOMAIN DOES NOT RESOLVE, because it was written to treat "unreachable" as "not
    disproven". That is right for withdrawal and wrong as a verify gate.
 3. IF THE NEW CITATION FAILS, THE OLD ONE STAYS. We are never worse off than before the
    round. The old citation was merely unconfirmed; an unconfirmed citation beats none.
 4. EVERY ACCEPTED CHANGE IS LOGGED old -> new. Contract 2.4: a verified value is never
    silently overwritten. Section 9: every cycle so far has contained a problem introduced BY
    a fix.

Evidence history is safe by construction: the `evidence` table is unique on
(event_id, field, source_url, origin), so a new citation ADDS a row and the previous one keeps
its verdict and quote. Nothing in the audit trail is overwritten.

Reports by default. Writes only with --apply.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store          # noqa: E402

# name fragment -> (resolution, deadline, note/evidence)
RESOLUTIONS = [
    ("ASCO Annual Meeting 2027",      "CORRECTED", "1/26/2027", ""),
    ("AVS 72nd International",        "CORRECTED", "5/18/2026", "main abstract deadline"),
    ("AppSec Israel 2026",            "CORRECTED", "10/6/2026", ""),
    ("Area41 Security",               "CORRECTED", "3/1/2026",  "primary CFP close"),
    ("FIRST 38th Annual",             "CORRECTED", "10/24/2025", ""),
    ("Electron Devices Meeting",      "CORRECTED", "8/3/2026",  ""),
    ("NAB Show 2027",                 "CORRECTED", "12/1/2026", "main call for speakers close"),
    ("SEMICON Japan 2026",            "CORRECTED", "8/21/2026", "main tech session paper deadline"),
    ("MedTech Conference 2026",       "CORRECTED", "8/19/2026", ""),
    ("WFCC 2026",                     "CORRECTED", "7/8/2026",  ""),
    ("LOPEC 2027", "DEFENDED", "12/4/2026",
     "OE-A Competition & LOPEC Call for Papers submission deadline: December 4, 2026"
     "||https://oe-a.org/topics/oe-a-working-groups/oe-a-competition/||2026-07-30"),
    ("OWASP Global AppSec EU 2026",   "UNCERTAIN", "", "site-wide placeholder date"),
    ("OWASP Global AppSec Europe 2026", "UNCERTAIN", "", "site-wide placeholder date"),
    ("OWASP Global AppSec USA 2026",  "UNCERTAIN", "", "site-wide placeholder date"),
]


# --------------------------------------------------------------- merge guard --
def _strict_ok(url: str) -> tuple[bool, str]:
    """Positive confirmation that a page EXISTS. Deliberately strict.

    Distinct from the "only 404/410 disprove" rule, which governs whether we may WITHDRAW a
    citation. Those are different questions and using one test for both is how a URL whose
    domain does not resolve came back as verified: an exception was read as "not disproven"
    and then used to assert "confirmed". Not-disproven is not confirmed.
    """
    import urllib.error
    import urllib.request
    if not (url or "").startswith("http"):
        return False, "not a url"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            code = getattr(r, "status", 200)
            return (200 <= code < 300), f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"unreachable: {type(e).__name__}"


def merge_citations(store, csv_path: str, apply: bool) -> int:
    """Decide which proposed citations are safe to take. Reports; writes only with apply."""
    import csv as _csv

    from src.cfp_monitor.verify import fetch_text, normalize_text

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        proposed = list(_csv.DictReader(fh))

    # UPSTREAM'S EVENT_ID IS NOT OURS. We recompute the canonical key on import (contract 5.4)
    # and the request CSV echoes back THEIR id, so a direct lookup matches nothing - the merge
    # would report rows accepted and then update zero of them, silently. Map through the seeds.
    from pathlib import Path as _P
    up_to_canon: dict[str, str] = {}
    for seed in sorted(_P("market_sheets").glob("*_seed.csv")):
        if seed.name == "grounding_seed.csv":
            continue
        with open(seed, encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                up = (row.get("EVENT_ID") or "").strip()
                canon = (row.get("EVENT_ID_CANON") or "").strip()
                if up and canon:
                    up_to_canon.setdefault(up, canon)

    current = {r["event_id"]: r for r in (dict(x) for x in store.db.execute(
        "select event_id, deadline, deadline_evidence_url, deadline_quote from grounding_facts"))}

    accepted, rejected, skipped = [], [], []
    for p in proposed:
        raw_id = (p.get("EVENT_ID") or "").strip()
        eid = up_to_canon.get(raw_id, raw_id)
        name = (p.get("CONFERENCE") or "")[:44]
        url = (p.get("DEADLINE_EVIDENCE_URL") or "").strip()
        quote = (p.get("DEADLINE_QUOTE") or "").strip()
        cur = current.get(eid)

        # A row we cannot place is never guessed at (2.5). Silently skipping it would be worse
        # than saying so - that is how a merge reports success having changed nothing.
        if cur is None:
            rejected.append((name, f"cannot match EVENT_ID to a row we hold ({raw_id[:40]})"))
            continue

        # RULE 1 - a blank never overwrites something we hold.
        if not url or not quote:
            skipped.append((name, "returned blank - keeping what we have"))
            continue

        # RULE 2 - it must survive OUR check, not theirs.
        ok, why = _strict_ok(url)
        if not ok:
            rejected.append((name, f"proposed URL did not resolve ({why})"))
            continue
        text, _ = fetch_text(url)
        if not text:
            rejected.append((name, "proposed page could not be read"))
            continue
        if normalize_text(quote[:60]) not in normalize_text(text):
            rejected.append((name, "quote is not on the proposed page"))
            continue

        accepted.append((eid, name, url, quote, p.get("DATE_CHANGED", ""),
                         (p.get("SUBMISSION DEADLINE") or "").strip(),
                         (cur or {}).get("deadline_evidence_url", ""),
                         (cur or {}).get("deadline", "")))

    print(f"\n{len(proposed)} proposed | {len(accepted)} accepted | "
          f"{len(rejected)} rejected | {len(skipped)} blank\n")
    for n, why in rejected:
        print(f"  REJECT  {n:<44} {why}")
    for n, why in skipped:
        print(f"  KEEP    {n:<44} {why}")
    # RULE 4 - every accepted change logged old -> new.
    for eid, n, url, q, changed, newdl, oldurl, olddl in accepted:
        print(f"  ACCEPT  {n:<44}")
        print(f"            url  {oldurl[:58]}")
        print(f"              -> {url[:58]}")
        if changed == "yes" and newdl != olddl:
            print(f"            DATE {olddl} -> {newdl}   (declared)")

    if not apply:
        print("\nreport only - re-run with --apply to write")
        return 0
    for eid, n, url, q, changed, newdl, oldurl, olddl in accepted:
        store.db.execute("""update grounding_facts
                            set deadline_evidence_url=?, deadline_quote=?
                            where event_id=?""", (url, q, eid))
        if changed == "yes" and newdl:
            store.db.execute("update grounding_facts set deadline=? where event_id=?",
                             (newdl, eid))
    store.db.commit()
    print(f"\nwrote {len(accepted)} accepted citation(s). "
          "Re-run build_evidence.py + audit_evidence.py to re-verify.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply upstream dispute resolutions.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--citations", help="CSV of replacement citations from upstream")
    a = ap.parse_args()

    if a.citations:
        store = Store(a.db)
        rc = merge_citations(store, a.citations, a.apply)
        store.close()
        return rc

    store = Store(a.db)
    db = store.db
    db.row_factory = __import__("sqlite3").Row
    counts = {"CORRECTED": 0, "DEFENDED": 0, "UNCERTAIN": 0, "not matched": 0}

    for frag, kind, deadline, note in RESOLUTIONS:
        rows = [dict(r) for r in db.execute(
            "SELECT * FROM grounding_facts WHERE name LIKE ?", ("%" + frag + "%",))]
        rows = [r for r in rows if r["verify_state"] == "contradicted"] or rows
        if not rows:
            print("  NOT MATCHED: {!r}".format(frag))
            counts["not matched"] += 1
            continue
        for r in rows:
            old = r["deadline"] or "(none)"
            print("  {:<10} {:<42} {:>11} -> {:>11}".format(
                kind, (r["name"] or "")[:40], old, deadline or "(blank)"))
            if not a.apply:
                continue
            if kind == "CORRECTED":
                db.execute(
                    "UPDATE grounding_facts SET deadline=?, verify_state='verified',"
                    " verify_detail=? WHERE event_id=?",
                    (deadline,
                     "[upstream] corrected to match our page evidence"
                     + (f" ({note})" if note else ""), r["event_id"]))
            elif kind == "DEFENDED":
                quote, url, as_of = note.split("||")
                db.execute(
                    "UPDATE grounding_facts SET deadline=?, deadline_quote=?,"
                    " deadline_evidence_url=?, source_as_of=?, verify_state='verified',"
                    " verify_detail=? WHERE event_id=?",
                    (deadline, quote, url, as_of,
                     "[upstream] defended with a labelled quote + deep link; our checker had"
                     " missed the zero-padded date on the page", r["event_id"]))
            else:  # UNCERTAIN
                db.execute(
                    "UPDATE grounding_facts SET deadline='', cfp_model='Not Announced',"
                    " verify_state='not_found', verify_detail=? WHERE event_id=?",
                    ("[upstream] neither side could establish a deadline"
                     + (f" ({note})" if note else ""), r["event_id"]))
            counts[kind] += 1

    if a.apply:
        db.commit()
        print("\nAPPLIED:", {k: v for k, v in counts.items() if v})
        states = dict(db.execute(
            "SELECT verify_state, COUNT(*) FROM grounding_facts GROUP BY verify_state").fetchall())
        print("verification states now:", states)
    else:
        print("\nDry run. Re-run with --apply to write.")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
