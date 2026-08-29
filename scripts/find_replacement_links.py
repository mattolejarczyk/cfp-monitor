"""Find the CURRENT submission page for conferences whose link no longer resolves.

An unreachable submission link almost never means an unreachable conference. Organisers
retire or move the call-for-papers page between editions, so the event is healthy and only
the URL we hold is stale. On 2026-08-09 that was 45 of 256 links (18%).

THREE FACTS, KEPT SEPARATE
Conflating them is how "45 dead links" came to sound like 45 broken conferences.

    LINK STATE   Live | Unreachable                     - an OBSERVATION
    OUTCOME      Replacement found | Candidate needs review | No live page found
    CFP STATE    Call open | Call closed | Announced, not yet open |
                 No speaking opportunity offered | Undetermined   - a CLAIM, with evidence

The CFP state is the one that matters to a customer and it is a claim like any other, so it
carries the sentence it was read from and the page it was read on. "The call has closed and
the page was retired" is a useful answer; "the link is dead" is not.

WHAT IT REUSES
    pipeline.run_urls      the FULL analysis - score-driven exploration, LLM extraction,
                           evidence-backed consolidation.
    consolidate._BASIS_PHRASE   the project's own evidence wording, so the customer sees the
                           phrasing the evidence layer produced, not a second vocabulary.
    verify.link_status     to confirm a proposal actually resolves

WHY NOT A CHEAPER KEYWORD PASS (tried on 2026-08-09, abandoned)
The first version skipped the LLM and ranked links by keyword score alone, to spend nothing.
It proposed `terrapinn.com/about-us`, a news article, and - after tightening - two individual
SPEAKER PROFILE pages and a speaker lineup. Zero useful results in six.

Not a tuning problem. Keyword scoring cannot distinguish "the page where you submit" from "a
page about speakers"; that is a semantic judgement, and it is exactly why the pipeline has an
extraction step. Skipping it rebuilt a weaker copy of an existing tool - the failure
`docs/operations/TOOLING.md` exists to prevent.

COST. Uses the OpenRouter/deepseek key, NOT the Gemini key - it cannot touch the grounded
research quota. Cents for all 45. Time is the real cost, up to `per_site_timeout_s` per site.

WHAT IT DOES NOT DO
Writes nothing back. `SUBMISSION URL` is upstream's field (contract section 3), so the output
is a CORRECTION offered through the defend-or-correct loop. Attach the CSV to the hand-back.

    python scripts/find_replacement_links.py --db cfp_monitor.db --out replacements.csv
    python scripts/find_replacement_links.py --db cfp_monitor.db --limit 5   # try a few first
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.config import Settings                      # noqa: E402
from src.cfp_monitor.consolidate import _BASIS_PHRASE            # noqa: E402
from src.cfp_monitor.pipeline import run_urls                    # noqa: E402
from src.cfp_monitor.fetch import close_fallback_browser         # noqa: E402
from src.cfp_monitor.scoring import normalize_url                # noqa: E402
from src.cfp_monitor.verify import link_status                   # noqa: E402

# Classify a proposal before offering it. The pipeline finds a plausible page; it does not
# know our contract. On the 2026-08-09 run it returned 23 proposals of which 8 were wrong,
# including two the contract forbids outright:
#   * IBC -> the Accelerator programme, when the row is Technical Papers. Section 10: one
#     event's several calls never share evidence.
#   * Troopers -> the bare homepage. R3: never substitute a shallower URL.
# The rest were speaker listings and a site search page.
#
# So: reject what is structurally wrong, mark CONFIDENT only when the URL says how to submit,
# and send everything else to a human rather than to upstream.
REJECT_PATH = ("/search", "__search", "/speakers", "/speaker-list", "/full-speaker-list",
               "/past-speakers", "/attendees", "/sponsors", "/exhibitors", "/about")
SUBMIT_SIGNAL = ("submit", "call-for", "call_for", "callforpapers", "cfp", "apply",
                 "proposal", "abstract", "speaker-form", "become-a-speaker", "presenters",
                 "papers", "nominat")
FORM_HOSTS = ("hsforms.com", "jotform.com", "wufoo.com", "docs.google.com/forms",
              "mirasmart.com", "papercept.net", "sessionize.com", "pretalx.com",
              "easychair.org", "oxfordabstracts.com", "cvent.com")


# What the CALL is doing, separate from whether our URL resolves. Conflating the two is how
# "45 dead links" came to imply 45 broken conferences. An unreachable URL is an OBSERVATION;
# why it is unreachable is a CLAIM, and a claim needs evidence like any other (contract 2.1).
#
# Mapped from the pipeline's own status_basis, so the wording the customer sees is the wording
# the evidence layer produced - not a second vocabulary invented here.
CFP_STATE = {
    "explicit_closed": "Call closed",
    "explicit_open": "Call open",
    "explicit_upcoming": "Announced, not yet open",
    "no_opportunity_found": "No speaking opportunity offered",
    "inferred_from_live_submission_form": "Call open",
    "opportunity_signals_no_live_form": "Call page exists, no live form",
    "insufficient_evidence": "Undetermined",
    "deadline_after_event_conflict": "Undetermined - page mixes editions",
    "inferred_open_but_deadline_past": "Undetermined - page looks stale",
}


def cfp_state(res) -> tuple[str, str, str]:
    """(state, evidence sentence, page it was read on) - our claim about the CALL."""
    basis = getattr(res, "status_basis", "") or ""
    state = CFP_STATE.get(basis, "Undetermined")
    why = _BASIS_PHRASE.get(basis, basis or "no basis recorded")
    url = ""
    for e in (getattr(res, "evidence", None) or []):
        if getattr(e, "field", "") in ("cfp_status", "submission_url", "cfp_close_date"):
            url = getattr(e, "source_url", "") or ""
            if url:
                break
    return state, why, url


def classify(proposed: str) -> tuple[str, str]:
    """(verdict, why). CONFIDENT is safe to offer upstream; REVIEW needs a human."""
    u = (proposed or "").strip().lower()
    if not u:
        return "", ""
    parsed = urlparse(u)
    path = (parsed.path or "").rstrip("/")
    if path in ("", "/"):
        return "REJECT", "bare homepage - R3 forbids a shallower substitute"
    if any(b in u for b in REJECT_PATH) and not any(g in u for g in SUBMIT_SIGNAL):
        return "REJECT", "listing or search page, not a way to submit"
    if any(h in u for h in FORM_HOSTS):
        if "summary" in u or "register" in u:
            return "REVIEW", "form host, but the page looks like registration"
        return "CONFIDENT", "submission form host"
    if any(g in u for g in SUBMIT_SIGNAL):
        return "CONFIDENT", "path states how to submit"
    return "REVIEW", "plausible page but it does not say how to submit"


def dead_rows(db: str, limit: int | None) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        select g.event_id, g.name, g.submission_url, g.url, g.main_info_url
        from grounding_facts g
        join link_checks l on l.url = g.submission_url
        where l.state = 'dead'
        order by g.name""")]
    con.close()
    return rows[:limit] if limit else rows


def start_url_for(row: dict) -> str:
    """Where to start exploring. Prefer the event's own site; fall back to the dead link's
    own origin, which is still the right domain even when the path has gone."""
    for k in ("url", "main_info_url"):
        u = (row.get(k) or "").strip()
        if u.startswith("http"):
            return u
    p = urlparse(row["submission_url"])
    return f"{p.scheme}://{p.netloc}/"


async def hunt(rows: list[dict], settings: Settings) -> list[dict]:
    """Run the full pipeline over each conference's own site and take its submission_url.

    One site at a time rather than one big batch, so a single hanging site cannot cost the
    whole run and progress is visible while it works.
    """
    results: list[dict] = []
    for i, row in enumerate(rows, 1):
        name, dead = row["name"], row["submission_url"]
        start_url = start_url_for(row)
        print(f"[{i}/{len(rows)}] {name[:46]}", flush=True)
        print(f"        unreachable: {dead[:71]}", flush=True)
        rec = {"CONFERENCE": name, "EVENT_ID": row["event_id"], "UNREACHABLE URL": dead,
               "START URL": start_url, "LINK STATE": "Unreachable",
               "OUTCOME": "", "PROPOSED URL": "", "VERDICT": "", "WHY": "",
               "CFP STATE": "", "EVIDENCE": "", "EVIDENCE URL": "",
               "FOUND VIA": "", "HTTP": "", "NOTE": ""}
        try:
            res = (await run_urls([start_url], settings))[0]
        except Exception as exc:
            rec["NOTE"] = f"pipeline failed: {type(exc).__name__}: {exc}"[:150]
            results.append(rec); print(f"        -> {rec['NOTE'][:70]}", flush=True); continue

        st, why_ev, ev_url = cfp_state(res)
        rec["CFP STATE"], rec["EVIDENCE"], rec["EVIDENCE URL"] = st, why_ev, ev_url

        found = (res.submission_url.value or "").strip() if res.submission_url else ""
        if not found:
            rec["OUTCOME"] = "No live page found"
            results.append(rec); print("        -> nothing found", flush=True); continue

        # ABSOLUTISE BEFORE VERIFYING. The extractor can return a relative href, and on
        # 2026-08-28 one did: IRPS 2027 was proposed as "/abstract-submission". Upstream caught
        # it. The verification below silently did not happen - link_status cannot resolve a
        # relative path, returns something that is not 404/410, and the row passes as though it
        # had been checked. An unverifiable proposal presented as verified is worse than none.
        if not found.lower().startswith(("http://", "https://")):
            joined = urljoin(start_url, found)
            if not joined.lower().startswith(("http://", "https://")):
                rec["OUTCOME"] = "No live page found"
                rec["NOTE"] = f"proposal was not a resolvable URL: {found[:60]!r}"
                results.append(rec)
                print(f"        -> unresolvable proposal {found[:40]!r}", flush=True)
                continue
            print(f"        (relative {found[:34]!r} -> {joined[:56]})", flush=True)
            found = joined
        if normalize_url(found) == normalize_url(dead):
            rec["OUTCOME"] = "No live page found"; rec["NOTE"] = "only the same unreachable URL"
            results.append(rec); print("        -> same dead url", flush=True); continue

        # Verify the proposal before offering it. Proposing a second dead link would be
        # worse than proposing nothing.
        # Only 404/410 disprove a link (contract 5.2) - the SAME rule we apply to citations.
        # A first version rejected anything >= 400 and silently dropped four good proposals on
        # a transient 500 and a 405 (Method Not Allowed on HEAD, i.e. the page exists and just
        # refuses that verb). All four returned 200 minutes later.
        code, _ = link_status(found)
        rec["HTTP"] = code or ""
        if code in (404, 410):
            rec["NOTE"] = f"candidate does not exist (HTTP {code})"
            results.append(rec); print(f"        -> candidate dead ({code})", flush=True); continue

        verdict, why = classify(found)
        rec["VERDICT"], rec["WHY"] = verdict, why
        if verdict == "REJECT":
            rec["OUTCOME"] = "No live page found"
            rec["NOTE"] = f"candidate rejected: {why}"
            rec["PROPOSED URL"] = ""
            results.append(rec); print(f"        -> rejected ({why})", flush=True); continue
        rec["OUTCOME"] = ("Replacement found" if verdict == "CONFIDENT"
                          else "Candidate needs review")
        rec["PROPOSED URL"] = found
        ev = ""
        for e in (res.evidence or []):
            if getattr(e, "field", "") == "submission_url":
                ev = (getattr(e, "snippet", "") or "")[:90]
                break
        rec["FOUND VIA"] = ev or (f"{res.submission_platform} form"
                                  if res.submission_platform else "found on site")
        print(f"        -> {found[:74]}  [{code}]", flush=True)
        results.append(rec)
    await close_fallback_browser()
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Propose live replacements for dead links.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--out", default="replacement_links.csv")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    rows = dead_rows(a.db, a.limit)
    if not rows:
        print("No unreachable links recorded. Has weekly_verify.py run?")
        return 0

    settings = Settings()
    print(f"{len(rows)} dead link(s) to chase. No LLM calls; crawl only.\n")
    results = asyncio.run(hunt(rows, settings))

    conf = [r for r in results if r.get("VERDICT") == "CONFIDENT"]
    review = [r for r in results if r.get("VERDICT") == "REVIEW"]
    found = conf + review
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    print(f"\n{len(found)} of {len(results)} got a live replacement proposal")
    print(f"wrote {a.out}")
    print("\nThese are PROPOSALS. SUBMISSION URL is upstream's field (contract section 3) -")
    print("attach this to the hand-back as corrections, do not write it into the delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
