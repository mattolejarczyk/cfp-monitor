"""Fail the build when a script re-implements site-walking instead of calling sitewalk.

THE RULE THIS REPLACES ALREADY EXISTED. The cfp-protocol skill says: "state which stage you are
working in and which existing tool covers it. If none does, say so explicitly before writing
anything new." It was skipped three times on 2026-08-29 - not from disagreement, but because
under time pressure "fix upstream's script" did not feel like writing new code.

A rule you must remember is not a control. This one fails the suite.

WHY AN ALLOW-LIST RATHER THAN A CLEAN SWEEP
Four scripts already contain their own copies. Refactoring all of them at once, on the day the
duplication was found, is exactly the kind of large uninstrumented change this project keeps
getting hurt by. So the existing offenders are listed by name with their debt recorded, and the
test fails on anything NOT on that list. The list may shrink; it must never grow.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Scripts that owned crawling logic before sitewalk existed. Migrate and delete from this list.
# Adding a name here is a decision to duplicate, and should be argued for in review.
PENDING_MIGRATION = {
    "investigate_event.py":      "the original; its discover_links is where the fixes were made",
    "probe_menu_links.py":       "measures what is behind menu links; predates sitewalk",
    "find_replacement_links.py": "delegates most crawling to pipeline.run_urls already",
    "find_event_pages.py":       "small, same-site check only",
    "diagnose_unread.py":        "classifies fetch failures rather than walking a site",
    "recheck_dead_links.py":     "single-URL browser check, no walking",
    "weekly_verify.py":          "calls link_status per URL, no walking",
    "extract_citations.py":      "fetches candidate pages it is handed",
    "extract_sponsor_quotes.py": "fetches the one page upstream supplied",
    "accept_delivery.py":        "the gate fetches cited pages; check 3 is its own concern",
    "check_dns.py":              "DNS only, deliberately no fetch",
}

# The moves that mean "I am walking a site myself".
WALKING = (
    re.compile(r"\burljoin\s*\(", re.I),
    re.compile(r"""href=\\?["']|\.get\(["']href["']\)""", re.I),
    re.compile(r"\bnetloc\b"),
)
FETCHING = re.compile(r"urllib\.request\.urlopen|_render_with_consent|requests\.get")


def _scripts():
    for p in sorted((ROOT / "scripts").glob("*.py")):
        yield p


def test_no_new_script_walks_a_site_on_its_own():
    """A script that joins URLs, reads hrefs AND inspects netloc is walking a site."""
    offenders = []
    for p in _scripts():
        if p.name in PENDING_MIGRATION:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        if sum(1 for pat in WALKING if pat.search(src)) >= 2:
            offenders.append(p.name)
    assert not offenders, (
        "These scripts re-implement site-walking. Use src/cfp_monitor/sitewalk.py "
        f"(rank_links / plan / same_site): {offenders}\n"
        "If duplication is genuinely necessary, add the file to PENDING_MIGRATION with a reason."
    )


def test_the_allow_list_only_shrinks():
    """Eleven known offenders on 2026-08-29. A rising number means the debt is growing."""
    assert len(PENDING_MIGRATION) <= 11, (
        f"PENDING_MIGRATION has grown to {len(PENDING_MIGRATION)}. It is a record of debt, "
        "not a place to file new duplication.")
    for name, why in PENDING_MIGRATION.items():
        assert why.strip(), f"{name} is allow-listed without a reason"


def test_allow_listed_scripts_still_exist():
    """A stale allow-list quietly permits a name nobody is watching."""
    missing = [n for n in PENDING_MIGRATION if not (ROOT / "scripts" / n).exists()]
    assert not missing, f"allow-listed but gone - remove them: {missing}"


def test_sitewalk_ranks_rather_than_filters():
    """The defect that discarded 119 real links: a link with no keyword must still be a
    candidate, just a lower-ranked one."""
    from src.cfp_monitor import sitewalk
    anchors = [{"href": "https://conf.example/forum", "text": "FORUM"},
               {"href": "https://conf.example/call-for-papers", "text": "Call for Papers"}]
    ranked = sitewalk.rank_links(anchors, "https://conf.example/")
    urls = [u for _s, u, _l in ranked]
    assert len(ranked) == 2, "a link with no keyword must still be a candidate"
    assert urls[0].endswith("call-for-papers"), "the relevant one must rank first"


def test_sitewalk_prefers_real_links_over_guesses():
    """Guessing is the last resort, not the opening move."""
    from src.cfp_monitor import sitewalk
    urls, how = sitewalk.plan([{"href": "https://conf.example/programme", "text": "Programme"}],
                              "https://conf.example/")
    assert "own navigation" in how and urls[0].endswith("programme")
    urls, how = sitewalk.plan([], "https://conf.example/")
    assert "guessed paths" in how, "with no links at all, say so plainly"


def test_same_site_handles_two_part_tlds():
    """The eng. vs www. case that discarded 118 of 119 links."""
    from src.cfp_monitor import sitewalk
    assert sitewalk.same_site("https://eng.robotworld.or.kr/x", "https://www.robotworld.or.kr/")
    assert sitewalk.same_site("https://a.example.co.uk/x", "https://www.example.co.uk/")
    assert not sitewalk.same_site("https://example.com/x", "https://other.com/")
