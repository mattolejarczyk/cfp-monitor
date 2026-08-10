"""Find the CURRENT submission page for conferences whose link has died.

A dead submission link almost never means a dead conference. Organisers retire or move the
call-for-papers page between editions, so the event is healthy and only the URL we hold is
stale. On 2026-08-09, 45 of 256 links (18%) were in that state.

Reporting them is not the same as fixing them. This closes the loop: for each dead link,
explore the conference's own site and propose the live page that replaces it.

WHAT IT REUSES
    pipeline.run_urls      the FULL analysis - score-driven exploration, LLM extraction,
                           evidence-backed consolidation. Returns submission_url as a Fact
                           carrying the page it was read on.
    verify.link_status     to confirm the proposal actually resolves

WHY NOT A CHEAPER KEYWORD PASS (tried on 2026-08-09, abandoned)
The first version skipped the LLM and ranked links by keyword score alone, to spend nothing.
It proposed `terrapinn.com/about-us`, a news article, and - after tightening - two individual
SPEAKER PROFILE pages and a speaker lineup. Zero useful results in six.

The reason is not a tuning problem. Keyword scoring cannot distinguish "the page where you
submit" from "a page about speakers"; that is a semantic judgement, and it is exactly why the
pipeline has an extraction and consolidation step. Skipping it rebuilt a weaker copy of a tool
that already existed, which is the specific failure `docs/operations/TOOLING.md` exists to
prevent.

COST. Uses the OpenRouter/deepseek key, NOT the Gemini key - it cannot touch the grounded
research quota. Roughly a few LLM calls per site at deepseek prices: cents for all 45. Time
is the real cost, at up to `per_site_timeout_s` per conference.

WHAT IT DOES NOT DO
Writes nothing back. `SUBMISSION URL` is upstream's field (contract section 3), so the
output is a CORRECTION offered through the normal defend-or-correct loop - it turns a
hand-back that says "45 links are broken" into one that says "and here are the replacements
we found". Attach the CSV to the hand-back.

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
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.config import Settings                      # noqa: E402
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
        print(f"        dead: {dead[:78]}", flush=True)
        rec = {"CONFERENCE": name, "EVENT_ID": row["event_id"], "DEAD URL": dead,
               "START URL": start_url, "PROPOSED URL": "", "VERDICT": "",
               "WHY": "", "FOUND VIA": "", "HTTP": "", "NOTE": ""}
        try:
            res = (await run_urls([start_url], settings))[0]
        except Exception as exc:
            rec["NOTE"] = f"pipeline failed: {type(exc).__name__}: {exc}"[:150]
            results.append(rec); print(f"        -> {rec['NOTE'][:70]}", flush=True); continue

        found = (res.submission_url.value or "").strip() if res.submission_url else ""
        if not found:
            rec["NOTE"] = "pipeline found no submission page on the site"
            results.append(rec); print("        -> nothing found", flush=True); continue
        if normalize_url(found) == normalize_url(dead):
            rec["NOTE"] = "pipeline returned the same dead URL"
            results.append(rec); print("        -> same dead url", flush=True); continue

        # Verify the proposal before offering it. Proposing a second dead link would be
        # worse than proposing nothing.
        code, _ = link_status(found)
        rec["HTTP"] = code or ""
        if not code or code >= 400:
            rec["NOTE"] = f"candidate did not resolve (HTTP {code})"
            results.append(rec); print(f"        -> candidate dead ({code})", flush=True); continue

        verdict, why = classify(found)
        rec["VERDICT"], rec["WHY"] = verdict, why
        if verdict == "REJECT":
            rec["NOTE"] = f"rejected: {why}"
            rec["PROPOSED URL"] = ""
            results.append(rec); print(f"        -> rejected ({why})", flush=True); continue
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
        print("No dead links recorded. Has weekly_verify.py run?")
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
