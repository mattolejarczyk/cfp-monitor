"""The per-client page: scoped to one client, with an "updated since" view.

WHAT THIS IS NOT, and the correction that produced it. An earlier version opened with a "You
asked, we answered" block, on the reading that `SUBMISSION DATE VERIFIED = 'Needs Verification'`
was a request aimed at us. It is not. It is **Nicolia's team's own default marker**, meaning
their person still has to eyeball the row. We inspect every row automatically whether or not it
carries that flag, and what we produce is INPUT to their manual check, not an answer to a
question they asked.

One label was worse than the framing: rows we could not match were shown as "not tracked" with
"tell us to add it". Those events are in their sheet and in our database - they are relevant by
definition, and the work is ours. Putting our coverage gap to the customer as a request was
backwards.

What survives is the useful half: the page is scoped to one client, and it can answer "what has
moved since I last looked".
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")


def test_the_asked_and_answered_block_is_gone():
    """It misread the workflow. Needs Verification is their marker, not our inbox."""
    assert "You asked, we answered" not in SRC
    assert "render_client_view" not in SRC
    assert "__CLIENTVIEW__" not in SRC
    assert not (ROOT / "src" / "cfp_monitor" / "client_view.py").exists(), \
        "the module should be removed, not left as dead code"


def test_no_label_asks_the_customer_to_fix_our_coverage():
    """'Not tracked - tell us to add it' put our gap on them. Those conferences are in their
    sheet, so they are relevant by definition and the work item is ours."""
    assert "Tell us to add it" not in SRC
    assert "not tracked" not in SRC.lower().replace("not tracked in", "")


def test_the_page_can_be_scoped_to_a_set_of_markets():
    """Two pages are wanted, not one per client: the markets with a customer, and everything.
    Scope decides what EXISTS on the page; the chips decide what is shown."""
    assert "--markets" in SRC
    assert "scope_label" in SRC


def test_market_scoping_keeps_the_chips():
    """A two-market page must still let a reader narrow to one. Removing the chips would make
    the scope and the filter the same control, and lose the comparison."""
    assert "const mkts=[...new Set(DATA.map(r=>r.m))].sort();" in SRC
    assert "const inMkt = r => !active.size || active.has(r.m);" in SRC


def test_an_unknown_market_name_is_refused_not_silently_empty():
    assert "unknown market(s)" in SRC
    assert "naming mismatch, not an empty market" in SRC


def test_the_page_can_still_be_scoped_to_one_client():
    """Kept for the platform, where isolation is per client rather than per market."""
    assert "--client" in SRC
    assert "client_conferences where client_key = ?" in SRC


def test_scoping_happens_before_anything_is_computed():
    """Filtering afterwards would leave the counts, the urgency banner and the market chips
    describing rows the client cannot see."""
    scope_at = SRC.index("SCOPE FIRST")
    build_at = SRC.index("data = build(rows")
    assert scope_at < build_at


def test_scoping_to_zero_rows_raises_rather_than_writing_an_empty_page():
    assert "left NO rows of" in SRC and "not a client who tracks nothing" in SRC


def test_there_is_an_updated_since_view_and_it_is_adjustable():
    """The question a weekly reader actually has. Every other view describes the CURRENT
    state; none described a change."""
    assert "'recent'" in SRC and "Updated since" in SRC
    assert "let SINCE" in SRC, "must be mutable or the date box is decorative"
    assert "$('fsince').oninput" in SRC
    assert "id=\"fsince\"" in SRC


def test_clearing_the_date_box_falls_back_rather_than_matching_everything():
    """An empty comparison string makes every row match, and the view silently becomes
    'everything' while still being labelled 'updated since'."""
    assert "$('fsince').value || '__SINCE__'" in SRC


def test_the_since_default_is_a_week():
    """The rhythm the customer reads on."""
    assert "timedelta(days=7)" in SRC


def test_source_as_of_reaches_the_page():
    """Without it there is nothing to filter on."""
    assert "'SOURCE_AS_OF'" in SRC
    assert "'asof': d['SOURCE_AS_OF']" in SRC


def test_the_page_never_opens_empty():
    """Arnica has nothing closing this month, so the intended landing view was empty and the
    page opened on 'Nothing matches those filters' - which reads as a broken product rather
    than a quiet month."""
    assert "A page must never open empty" in SRC
    assert "for (const k of ['soon','urgent','open','recent','watching','all'])" in SRC
    assert "if (k === 'all') view = 'all';" in SRC, "Everything is the floor"


def test_the_landing_view_counts_through_the_market_filter_like_the_chips_do():
    """An existing guard forbids counting the whole database instead of the filtered set - a
    bug the customer found live, where picking Utility left 'Need to Verify 81' above a
    four-row table. The landing-view picker must obey the same rule."""
    assert "DATA.filter(r=>inMkt(r)&&v.f(r)).length) { view = k; break; }" in SRC
    assert SRC.index("const inMkt =") < SRC.index("for (const k of ['soon'"), \
        "inMkt is a const - calling it before its definition is a temporal-dead-zone error"
