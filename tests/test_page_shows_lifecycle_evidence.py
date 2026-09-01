"""The customer page must show WHY a conference is no longer running, not just assert it.

Until 2026-09-01 `build_review_page.py` read neither `LIFECYCLE_QUOTE` nor
`LIFECYCLE_EVIDENCE_URL`. R16 exists because a discontinuation is the most consequential claim
in the pipeline - it removes a conference from a customer's list - and an amendment was spent
making upstream evidence it. The renderer then dropped the evidence on the floor.

ESF MENA is the row that found it. Its delivery record carries europetro.com's own sentence:

    "Due to the current situation, we have taken the decision not to hold ESF MENA as a
     standalone event in 2026."

The customer holds an ACCEPTANCE to that event and a $12,500 sponsorship decision, and their
copy of the page could not show them that sentence. The gap was papered over by writing them a
separate alert document - which is the tell. A finding that needs its own document is a finding
the product failed to surface.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SRC = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")


def test_both_lifecycle_fields_are_in_the_whitelist():
    """`build` reads every row as {k: r.get(k) for k in FIELDS}. A column missing from FIELDS is
    silently EMPTY downstream however full the delivery is.

    The first version of this change added the render and not the whitelist entries, and used
    `d.get('LIFECYCLE_QUOTE', '')` - which looks careful and was precisely what hid the bug. The
    page shipped `"lq": ""` for ESF MENA while the delivery held the organiser's sentence, and a
    reader would have concluded there was no evidence rather than that we dropped it."""
    i = SRC.index("FIELDS =")
    fields_block = SRC[i:SRC.index("MARKET_LABEL")]
    assert "'LIFECYCLE_QUOTE'" in fields_block
    assert "'LIFECYCLE_EVIDENCE_URL'" in fields_block


def test_both_lifecycle_fields_reach_the_page():
    assert "'lq': d['LIFECYCLE_QUOTE']" in SRC
    assert "'lev': d['LIFECYCLE_EVIDENCE_URL']" in SRC


def test_the_quote_is_rendered():
    assert "r.lq?" in SRC, "the quote must be rendered, not merely carried into the JSON"
    assert "esc(r.lq)" in SRC, "and escaped, like every other quote on the page"


def test_the_source_is_linked_when_there_is_one():
    """A quote with its source beats a quote without. The link is what lets a customer check
    a claim that costs them a conference."""
    i = SRC.index("r.lq?")
    block = SRC[i:i + 420]
    assert "esc(r.lev)" in block and "href" in block


def test_an_unsourced_lifecycle_quote_says_so():
    """The same standard already applied to DEADLINE_QUOTE: without a source URL, a heading that
    implies we read it off the organiser's page is a claim we cannot support. It is exactly the
    standard we hold upstream to under R16."""
    i = SRC.index("r.lq?")
    block = SRC[i:i + 420]
    assert "no source page recorded" in block


def test_an_older_delivery_still_renders():
    """Deliveries at 38 columns predate the v1.5 lifecycle fields. `build` uses
    `r.get(k) or ''` over FIELDS, so a missing column becomes an empty string rather than a
    KeyError, and the section simply does not render. Assert that shape survives - the fix must
    not become a bare r['LIFECYCLE_QUOTE'] on the raw CSV row."""
    i = SRC.index("d = {k: (r.get(k) or '').strip() for k in FIELDS}")
    assert i > 0, "the row reader must keep tolerating absent columns"
    assert "r['LIFECYCLE_QUOTE']" not in SRC, "never read the raw row directly"


def test_a_row_with_no_lifecycle_evidence_renders_nothing():
    """Most rows are running normally and have neither field. They must not gain an empty
    heading - the section is conditional on the quote existing."""
    i = SRC.index("r.lq?")
    assert SRC[i - 3:i].strip().endswith("${"), "must be a conditional template expression"
    block = SRC[i:i + 460]
    assert block.rstrip().endswith(":''}") or ":''}" in block
