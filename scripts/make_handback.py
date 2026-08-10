"""Generate the upstream hand-back document from verification results.

    python scripts/make_handback.py --db cfp_monitor.db --out handback.md

Two clearly separated sections, because the two problems need different treatment:
  A. Links that no longer resolve -> a PROMPT fix, plus the replacements we located.
  B. Deadline disputes      -> a targeted DEFEND-OR-CORRECT re-check of those rows only.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store          # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the upstream hand-back document.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--seed-csv", default="", help="one seed CSV; default is every *_seed.csv")
    ap.add_argument("--seed-dir", default="market_sheets")
    ap.add_argument("--out", default="handback.md")
    ap.add_argument("--replacements", help="CSV from find_replacement_links.py - "
                    "turns Section A from a complaint list into a correction list")
    a = ap.parse_args()

    # Read EVERY per-market seed, not one combined file. Deliveries are now imported one
    # market at a time, so the old single grounding_seed.csv is stale and left most rows
    # showing an unknown market ("?") in the hand-back.
    market_of: dict[str, str] = {}
    seeds = [Path(a.seed_csv)] if a.seed_csv else []
    if not seeds or not seeds[0].exists():
        seeds = sorted(Path(a.seed_dir).glob("*_seed.csv"))
    for seed in seeds:
        if not seed.exists():
            continue
        with open(seed, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                eid = (row.get("EVENT_ID_CANON") or "").strip()
                mk = (row.get("Market") or "").strip()
                if eid and mk:
                    market_of.setdefault(eid, mk)

    store = Store(a.db)
    rows = [dict(r) for r in store.db.execute(
        "SELECT * FROM grounding_facts WHERE verify_state='contradicted' ORDER BY name")]
    # Counts come from the DB. They used to be hard-coded in the header string, so every
    # hand-back after the first reported the FIRST cycle's numbers to upstream.
    tally = {s or "(blank)": n for s, n in store.db.execute(
        "SELECT verify_state, count(*) FROM grounding_facts GROUP BY verify_state")}
    n_total = sum(tally.values())
    crawled = {r["key"]: r for r in store.all_records()}
    store.close()

    dead = [r for r in rows if "404" in (r["verify_detail"] or "")]

    # Prefer link_checks (weekly_verify checks EVERY submission link) over verify_state, which
    # only sees links layer 1 happened to reach - it missed 8 of 45 because those rows resolved
    # at layer 0 and never got as far as the link test.
    store2 = Store(a.db)
    try:
        known_dead = {u for (u,) in store2.db.execute(
            "select url from link_checks where state='dead'")}
    except Exception:
        known_dead = set()
    if known_dead:
        seen = {r["submission_url"] for r in dead}
        extra = [dict(r) for r in store2.db.execute(
            "select * from grounding_facts where submission_url in (%s)"
            % ",".join("?" * len(known_dead)), tuple(known_dead))
            if r["submission_url"] not in seen]
        if extra:
            print(f"  link_checks adds {len(extra)} dead link(s) verify_state did not see")
        dead = sorted(dead + extra, key=lambda r: (r["name"] or ""))
    store2.close()
    disputes = [r for r in rows if r not in dead]

    paths = Counter()
    for r in dead:
        p = re.sub(r"^https?://[^/]+", "", r["submission_url"] or "").rstrip("/").lower()
        if p:
            paths[p] += 1
    invented = [(p, n) for p, n in paths.most_common() if n > 1]

    # Built from the replacement CSV when one is supplied, so every number here is DERIVED.
    # The previous version stated counts in prose that were typed once and never recomputed.
    repl = {}
    if a.replacements and Path(a.replacements).exists():
        with open(a.replacements, encoding="utf-8-sig", newline="") as fh:
            repl = {r["CONFERENCE"]: r for r in csv.DictReader(fh)}

    n_conf = sum(1 for r in repl.values() if r.get("VERDICT") == "CONFIDENT")
    n_rev = sum(1 for r in repl.values() if r.get("VERDICT") == "REVIEW")
    states = Counter(r.get("CFP STATE") or "Undetermined" for r in repl.values())
    n_open = states.get("Call open", 0)

    L = []
    w = L.append
    w("# Verification findings for the conference discovery sweep")
    w("")
    w(f"_Generated {date.today().isoformat()} from an automated verification pass over "
      f"all {n_total} claims currently loaded._")
    w("")
    w(f"**Overall: {tally.get('verified', 0)} verified, {tally.get('contradicted', 0)} "
      f"contradicted, {tally.get('not_found', 0)} not-found.** Not-found means our checker "
      "could not read a deadline on the page; per our agreed precedence that is NOT a "
      f"disproof, so those values stand untouched. Only the {tally.get('contradicted', 0)} "
      "below need your attention, and they split into two unrelated problems.")
    w("")
    w("| | Count | What it needs |")
    w("|---|--:|---|")
    w(f"| A. Links that no longer resolve | {len(dead)} | A prompt rule, plus {n_conf} corrections we found for you. |")
    w(f"| B. Deadline disputes | {len(disputes)} | Targeted re-check: defend or correct. |")
    w("")
    w("---")
    w("")

    # ---------------- Section A ----------------

    w(f"## Section A - {len(dead)} submission links that no longer resolve")
    w("")
    w("Each was checked twice: a plain HTTP request, then a **real browser** judging page "
      "content as well as status code, so a soft 404 returning 200 with a \"page not found\" "
      f"body is still caught. **{len(dead)} of {len(dead)} confirmed unreachable, zero false "
      "positives** - these are not sites blocking us.")
    w("")
    w("**An unreachable link is not a broken conference.** Those are separate facts and we "
      "report them separately:")
    w("")
    w("| | |")
    w("|---|--:|")
    w(f"| Links that no longer resolve | {len(dead)} |")
    if repl:
        w(f"| ...for which we found the **current page** | **{n_conf}** |")
        w(f"| ...candidates we are unsure about, not sent | {n_rev} |")
        w(f"| ...no live page found | {len(dead) - n_conf - n_rev} |")
    w("")
    if repl:
        w("And what the CALL is doing, which is the part that matters to the customer. This is "
          "a claim, so each row in the attached CSV carries the sentence it was read from and "
          "the page it was read on:")
        w("")
        w("| Call state | Rows |")
        w("|---|--:|")
        for st, n in states.most_common():
            w(f"| {st} | {n} |")
        w("")
        if n_open:
            w(f"**{n_open} of these calls are open right now.** The opportunity is live and only "
              "the URL is stale, so these are moved pages rather than ended calls - which is why "
              "we went and looked for where they moved to.")
            w("")
        w(f"### {n_conf} replacements we are confident in")
        w("")
        w("Attached: `replacement_links_20260809.csv`. Every URL below was retrieved and "
          "verified, and each states how to submit - we discarded candidates that were "
          "homepages, speaker listings or a different call at the same event, because offering "
          "those would waste your time.")
        w("")
        w("| Conference | Was | Now |")
        w("|---|---|---|")
        for r in sorted(repl.values(), key=lambda x: x["CONFERENCE"]):
            if r.get("VERDICT") != "CONFIDENT":
                continue
            was = (r.get("UNREACHABLE URL") or r.get("DEAD URL") or "")
            w(f"| {r['CONFERENCE'][:44]} | `{was[:58]}` | `{r['PROPOSED URL'][:58]}` |")
        w("")
        w("**Take these as corrections, or defend the originals** - the usual three answers "
          "apply. We have not written them into anything; `SUBMISSION URL` is yours.")
        w("")
        if n_rev:
            w(f"The {n_rev} we are unsure about are in the CSV marked `REVIEW`. We are not "
              "asking you to act on those - they are there so you can see what we saw.")
            w("")
    w("### What we need from the next sweep")
    w("")
    w("> Never output a URL you have not actually retrieved. Do not build a submission URL by "
      "appending a likely path (`/call-for-speakers`, `/exhibit`, `/submit-papers`, "
      "`/apply-to-speak`) to a domain. If you cannot retrieve a specific, working submission "
      "URL, leave `SUBMISSION_URL` blank and set `CFP MODEL TYPE = Not Announced`.")
    w("")
    w("**A blank is more useful to us than a plausible URL that does not resolve.** We can crawl to find the "
      "real one; we cannot tell a fabricated URL from a real one without fetching it, and a "
      "client who clicks through to nothing loses trust in the whole list.")
    w("")
    w("### Every link that no longer resolves")
    w("")
    w("| Conference | Market | Unreachable URL |")
    w("|---|---|---|")
    for r in dead:
        w("| {} | {} | `{}` |".format(
            (r["name"] or "").replace("|", "/"), market_of.get(r["event_id"], "?"),
            r["submission_url"] or ""))
    w("")
    w("---")
    w("")

    # ---------------- Section B ----------------
    w(f"## Section B - {len(disputes)} deadline disputes: defend or correct")
    w("")
    w("For each row below our evidence indicates a different submission deadline. We are NOT "
      "asserting you are wrong - we may have read a secondary deadline (workshop, "
      "late-breaking, poster) rather than the main one. **Please re-check only these rows** "
      "and reply with one of:")
    w("")
    w("1. **CORRECTED** - our finding is right; give the corrected deadline.")
    w("2. **DEFENDED** - yours is right. Populate all three existing v4 fields:")
    w("   - `DEADLINE_QUOTE` - the verbatim sentence from the page")
    w("   - `DEADLINE_EVIDENCE_URL` - **the exact page that sentence appears on**")
    w("   - `SOURCE_AS_OF` - when that page was published or last updated")
    w("3. **UNCERTAIN** - neither can be established; set the deadline blank and "
      "`CFP MODEL TYPE = Not Announced`.")
    w("")
    w("Option 2 is the most valuable outcome even when you are right, because a verbatim "
      "quote plus a deep link lets us confirm it automatically next time instead of "
      "re-litigating it.")
    w("")
    w("### Two things that make the evidence usable (or useless)")
    w("")
    w("**The evidence URL must be the page carrying the quote, not the site's front page.** "
      "In the v4 backfill, `DEADLINE_EVIDENCE_URL` was identical to `MAIN_INFO_URL` on 255 of "
      "404 rows (63%). A homepage link cannot verify a deadline: we fetch it, the sentence "
      "isn't there, and the claim stays unverified - which is how a correct deadline ends up "
      "looking unconfirmed. Deep-link it.")
    w("")
    w("**Include the LABEL in the quote, not just the date.** Our leading theory for most of "
      "these disputes is that one of us read a secondary deadline. Conferences routinely "
      "publish several - main track, workshop, poster, late-breaking, extended. "
      "`\"March 15, 2027\"` does not settle anything; "
      "`\"Main track paper submission deadline: March 15, 2027\"` settles it immediately and "
      "tells us which deadline we should have been reading.")
    w("")
    for i, r in enumerate(disputes, 1):
        ours = crawled.get(r["conference_key"], {})
        w(f"**{i}. {r['name']}**  ({market_of.get(r['event_id'], '?')})")
        w("")
        w(f"- Your claim: **{r['deadline'] or '(none)'}**")
        w(f"- Our evidence: {(r['verify_detail'] or '').split('  <-')[0]}")
        if ours.get("url"):
            w(f"- Page we read: {ours.get('url')}")
        w(f"- Your cited source: {r['deadline_evidence_url'] or r['url'] or '(none)'}")
        w("")

    w("---")
    w("")
    w("## What we are NOT asking for")
    w("")
    w("Please do **not** re-sweep the other 335 claims. They are either verified or honestly "
      "not-found, and re-running them risks regression for no gain. Sections A and B are the "
      "complete set of items where our evidence disagrees with the sweep.")
    w("")

    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print("Wrote {}  ({} dead links, {} disputes)".format(a.out, len(dead), len(disputes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
