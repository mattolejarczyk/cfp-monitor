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
# A grounded model can return the SEARCH TOOL'S redirect rather than the page it found. On the
# 2026-08-11 pilot, AORN came back as vertexaisearch.cloud.google.com/grounding-api-redirect/...
# It resolves, and the quote is reachable through it, so it passed every content check - but it
# is not the event's page. It is a temporary proxy that expires, and it fails R3 outright: the
# citation must be the page the sentence appears on. Nothing here can catch that by fetching,
# so it is a structural rule.
PROXY_HOSTS = ("vertexaisearch.cloud.google.com", "grounding-api-redirect",
               "webcache.googleusercontent.com", "translate.google.com",
               "r.jina.ai", "12ft.io", "outlook.safelinks.protection.outlook.com")


def _is_proxy(url: str) -> bool:
    u = (url or "").lower()
    return any(h in u for h in PROXY_HOSTS)


# A social post is not a citation, for the same reason a search redirect is not: it is not the
# event's page, and nothing about fetching it reveals the problem. Found 2026-08-11 - five rows
# in the delivery cited a Facebook page as where the deadline was read, and one pilot row tried
# to move a date on the strength of "a Facebook post by All Energy Australia". A feed is not
# stable evidence: the post scrolls away, the page still resolves, and the citation quietly
# stops supporting anything. R3 wants the page the sentence appears on.
SOCIAL_HOSTS = {"facebook.com", "m.facebook.com", "fb.com", "twitter.com", "x.com",
                "instagram.com", "linkedin.com", "threads.net", "t.me", "tiktok.com",
                "reddit.com", "medium.com", "youtube.com", "youtu.be"}


def _is_social(url: str) -> bool:
    """Exact host match, never a substring: 'x.com' in a URL also matches pretalx.com and
    interphex.com, which are a legitimate CFP platform and an event's own site. A sloppy LIKE
    reported eight of these when there are five."""
    from urllib.parse import urlparse
    host = urlparse(url or "").netloc.lower()
    return host.removeprefix("www.") in SOCIAL_HOSTS


# One definition, shared with the extractor - see verify.is_homepage for why.
from src.cfp_monitor.verify import is_homepage as _is_homepage      # noqa: E402


def _strict_ok(url: str) -> tuple[bool, str]:
    """Positive confirmation that a page EXISTS. Deliberately strict.

    Retained for reporting; the merge decision now turns on CONTENT (can we read the page and
    is the quote on it), which is a stronger test than any status code.

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


def _seed_map(store) -> tuple[dict[str, str], list]:
    """upstream EVENT_ID -> our canonical id, plus the directories it was read from.

    UPSTREAM'S EVENT_ID IS NOT OURS. We recompute the canonical key on import (contract 5.4)
    and their files echo back THEIR id, so a direct lookup matches nothing - a merge would
    report rows accepted and then update zero of them, silently.

    Looks beside the DATABASE before the working directory. The seeds live in the live build's
    data root while these scripts are usually run from the repo, and a bare relative path found
    nothing there: the map came back empty, every row failed to resolve, and a run printed five
    per-row DATA rejections for what was purely a path problem. A config fault must not be able
    to impersonate a data fault.
    """
    import csv as _csv
    from pathlib import Path as _P

    roots, seen = [], set()
    for cand in (_P(getattr(store, "path", "") or ".").resolve().parent, _P.cwd()):
        d = cand / "market_sheets"
        if d.is_dir() and d not in seen:
            seen.add(d); roots.append(d)

    up_to_canon: dict[str, str] = {}
    for root in roots:
        for seed in sorted(root.glob("*_seed.csv")):
            if seed.name == "grounding_seed.csv":
                continue
            with open(seed, encoding="utf-8-sig", newline="") as fh:
                for row in _csv.DictReader(fh):
                    up = (row.get("EVENT_ID") or "").strip()
                    canon = (row.get("EVENT_ID_CANON") or "").strip()
                    if up and canon:
                        up_to_canon.setdefault(up, canon)
    return up_to_canon, roots


def retire_deadlines(store, csv_path: str, apply: bool) -> int:
    """Blank a deadline neither side can source, and say Not Announced instead.

    Separate from the hardcoded RESOLUTIONS list on purpose. That list is a record of one
    round's decisions and re-running it would re-apply its CORRECTED entries, overwriting
    deadlines the citation work has since improved - a fix from July silently undoing a
    verified value from August. Retiring a row must not require replaying history.

    CSV: EVENT_ID, CONFERENCE, REASON. The reason is stored, because "Not Announced" without
    one is indistinguishable from a row nobody has looked at (contract 2.6).
    """
    import csv as _csv

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(_csv.DictReader(fh))

    up_to_canon, _roots = _seed_map(store)
    current = {r["event_id"]: r for r in (dict(x) for x in store.db.execute(
        "select event_id, deadline, deadline_evidence_url from grounding_facts"))}
    if not current:
        print("REFUSING - no rows in grounding_facts. Point --db at the live database.")
        return 1

    done, missed = [], []
    for r in rows:
        raw = (r.get("EVENT_ID") or "").strip()
        eid = up_to_canon.get(raw, raw)
        name = (r.get("CONFERENCE") or "")[:46]
        reason = (r.get("REASON") or "").strip()
        cur = current.get(eid)
        if cur is None:
            missed.append((name, f"cannot place EVENT_ID ({raw[:40]})"))
            continue
        done.append((name, cur["deadline"] or "(already blank)", reason))
        if apply:
            store.db.execute(
                "UPDATE grounding_facts SET deadline='', cfp_model='Not Announced',"
                " verify_state='not_found', verify_detail=? WHERE event_id=?",
                (f"[retired] {reason}", eid))

    for name, old, reason in done:
        print(f"  RETIRE  {name:<46} {old} -> Not Announced")
        print(f"            {reason}")
    for name, why in missed:
        print(f"  SKIP    {name:<46} {why}")

    if apply:
        store.db.commit()
        print(f"\nretired {len(done)} deadline(s)")
    else:
        print(f"\n{len(done)} would be retired - re-run with --apply to write")
    return 0 if not missed else 1


def merge_citations(store, csv_path: str, apply: bool) -> int:
    """Decide which proposed citations are safe to take. Reports; writes only with apply."""
    import csv as _csv

    from src.cfp_monitor.verify import fetch_text, normalize_text

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        proposed = list(_csv.DictReader(fh))

    up_to_canon, roots = _seed_map(store)

    current = {r["event_id"]: r for r in (dict(x) for x in store.db.execute(
        "select event_id, deadline, deadline_evidence_url, deadline_quote from grounding_facts"))}

    # Refuse to grade anything against an empty table. Rejecting every row one by one looks
    # like upstream sent rubbish; it is indistinguishable, in the output, from the real thing.
    if not up_to_canon or not current:
        print("REFUSING TO MERGE - this is a setup problem, not a data problem.\n"
              f"  id map    : {len(up_to_canon)} entries from {len(roots)} market_sheets dir(s)\n"
              f"  db rows   : {len(current)} in grounding_facts\n"
              f"  db opened : {getattr(store, 'path', '?')}\n"
              "Point --db at the live database; the seeds are read from beside it.")
        return 1

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

        # A search-tool redirect is not a citation, however well it resolves (R3).
        if _is_proxy(url):
            rejected.append((name, "search-redirect URL, not the event's own page"))
            continue

        # Nor is a social post - same reason, different surface. See SOCIAL_HOSTS.
        if _is_social(url):
            rejected.append((name, "social media page, not the event's own page"))
            continue

        # R3 RUNS BOTH WAYS - never trade a deep page for a shallower one. A homepage can carry
        # the right date in a banner and still be worse evidence than what it would replace,
        # because it cannot show WHICH call the date belongs to. citation_fixes already refuses
        # to PROPOSE this; nothing stopped it arriving from upstream instead, and their pilot
        # shortlist for CCUS included the bare root of the site alongside the abstract page.
        if _is_homepage(url) and cur.get("deadline_evidence_url") \
                and not _is_homepage(cur["deadline_evidence_url"]):
            rejected.append((name, "homepage would replace a deeper citation we already hold"))
            continue

        # RULE 2 - it must survive OUR check, not theirs.
        #
        # CLIMB THE LADDER BEFORE REJECTING. Plain HTTP said 403 for amcoe.org on the pilot;
        # the browser read 16,675 characters of it. Rejecting on the cheap pass alone would
        # discard citations for being defended against automation rather than for being wrong -
        # the same error as treating a 403 as a dead link.
        text, _ = fetch_text(url)
        if not text:
            try:
                import asyncio as _aio
                import importlib.util as _ilu
                _s = _ilu.spec_from_file_location(
                    "_ae", Path(__file__).resolve().parent / "audit_evidence.py")
                _ae = _ilu.module_from_spec(_s)
                _s.loader.exec_module(_ae)
                text = _aio.run(_ae.escalate([url])).get(url, ("", ""))[0]
            except Exception:
                text = ""
        if not text:
            rejected.append((name, "page could not be read, even through the browser"))
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
        # RECORD THAT WE VERIFIED IT. Rule 2 above fetched this page and proved the quote is on
        # it - that IS a verification, and leaving verify_state alone meant the row kept a
        # stale 'not_found' or 'contradicted' from an earlier audit. Downstream that made
        # freshly verified rows look unbacked: refresh_delivery flagged Humanoids, Solid
        # Freeform and GreenBiz as unverified hours after we confirmed them by hand.
        store.db.execute("""update grounding_facts
                            set deadline_evidence_url=?, deadline_quote=?,
                                verify_state='verified', verify_detail=?
                            where event_id=?""",
                         (url, q, "[merge] quote confirmed on the cited page at merge time",
                          eid))
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
    ap.add_argument("--retire", help="CSV (EVENT_ID, CONFERENCE, REASON) of deadlines neither "
                                     "side can source - blanked and set Not Announced")
    a = ap.parse_args()

    if a.retire:
        store = Store(a.db)
        rc = retire_deadlines(store, a.retire, a.apply)
        raise SystemExit(rc)

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
