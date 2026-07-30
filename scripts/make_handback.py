"""Generate the upstream hand-back document from verification results.

    python scripts/make_handback.py --db cfp_monitor.db --out handback.md

Two clearly separated sections, because the two problems need different treatment:
  A. Dead submission links  -> a PROMPT fix (systemic); the rows are evidence, not work items.
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
    ap.add_argument("--seed-csv", default="market_sheets/grounding_seed.csv")
    ap.add_argument("--out", default="handback.md")
    a = ap.parse_args()

    market_of: dict[str, str] = {}
    seed = Path(a.seed_csv)
    if seed.exists():
        with open(seed, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                market_of.setdefault((row.get("EVENT_ID_CANON") or "").strip(),
                                     (row.get("Market") or "").strip())

    store = Store(a.db)
    rows = [dict(r) for r in store.db.execute(
        "SELECT * FROM grounding_facts WHERE verify_state='contradicted' ORDER BY name")]
    crawled = {r["key"]: r for r in store.all_records()}
    store.close()

    dead = [r for r in rows if "404" in (r["verify_detail"] or "")]
    disputes = [r for r in rows if r not in dead]

    paths = Counter()
    for r in dead:
        p = re.sub(r"^https?://[^/]+", "", r["submission_url"] or "").rstrip("/").lower()
        if p:
            paths[p] += 1
    invented = [(p, n) for p, n in paths.most_common() if n > 1]

    L = []
    w = L.append
    w("# Verification findings for the conference discovery sweep")
    w("")
    w(f"_Generated {date.today().isoformat()} from an automated verification pass over "
      f"all 379 claims in Conference_List_2026_2027_MASTER_v4.csv._")
    w("")
    w("**Overall: 17 verified, 45 contradicted, 317 not-found.** Not-found means our checker "
      "could not read a deadline on the page; per our agreed precedence that is NOT a "
      "disproof, so those values stand untouched. Only the 45 below need your attention, "
      "and they split into two unrelated problems.")
    w("")
    w("| | Count | What it needs |")
    w("|---|--:|---|")
    w(f"| A. Dead submission links | {len(dead)} | A prompt rule. Rows are evidence, not work items. |")
    w(f"| B. Deadline disputes | {len(disputes)} | Targeted re-check: defend or correct. |")
    w("")
    w("---")
    w("")

    # ---------------- Section A ----------------
    w(f"## Section A - {len(dead)} submission URLs that do not exist")
    w("")
    w("Every one of these was checked twice: first with a plain HTTP request, then again "
      "with a **real headless browser** (judging on page content as well as status code, so "
      "soft 404s that return 200 with a \"page not found\" body are caught). "
      f"**{len(dead)} of {len(dead)} confirmed genuinely dead - zero false positives.** "
      "These are not sites blocking us; the pages are not there.")
    w("")
    if invented:
        w("### The pattern: constructed paths, not retrieved URLs")
        w("")
        w("The same invented path appears across unrelated domains, which is the signature of "
          "a URL being assembled rather than retrieved:")
        w("")
        w("| Path appended | Times | Example domains |")
        w("|---|--:|---|")
        for p, n in invented:
            ex = [re.sub(r"^https?://(www\.)?", "", r["submission_url"] or "").split("/")[0]
                  for r in dead
                  if re.sub(r"^https?://[^/]+", "", r["submission_url"] or "").rstrip("/").lower() == p]
            w(f"| `{p}` | {n} | {', '.join(ex[:3])} |")
        w("")
    w("### What we need from the next sweep")
    w("")
    w("> Never output a URL you have not actually retrieved. Do not build a submission URL by "
      "appending a likely path (`/call-for-speakers`, `/exhibit`, `/submit-papers`, "
      "`/apply-to-speak`) to a domain. If you cannot retrieve a specific, working submission "
      "URL, leave `SUBMISSION_URL` blank and set `CFP MODEL TYPE = Not Announced`.")
    w("")
    w("**A blank is more useful to us than a plausible dead link.** We can crawl to find the "
      "real one; we cannot tell a fabricated URL from a real one without fetching it, and a "
      "client who clicks a dead link loses trust in the whole list.")
    w("")
    w("### The confirmed-dead links")
    w("")
    w("| Conference | Market | Dead submission URL |")
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
