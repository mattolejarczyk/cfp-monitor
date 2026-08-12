"""The customer review page - the one artefact Nicolia actually reads.

WHY THIS FILE EXISTS
615 lines, load-bearing, customer-facing, and until 2026-08-12 it had zero tests. Every fix to
it this week - dead-host suppression, the "cited page doesn't back the date" wording, deriving
Closed from the date, confidence deriving Projected over a stored Verified - was verified by a
human reading the output once and never again. On 2026-08-12 a dead link reached a page that
had been cleared as safe, and the cause was a line nobody could have caught by looking at
output that happened to be correct that day.

These tests encode the DECISIONS, not the rendering. What matters is never "the HTML looks
right" - it is "a link we know is dead is never offered as though it works", and "a projected
date can never wear a Verified badge". Those are the two ways this page can cost the customer
real money.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("brp", ROOT / "scripts" / "build_review_page.py")
brp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brp)


def row(**kw):
    """A delivery row with everything blank unless the test cares about it."""
    base = {k: "" for k in brp.FIELDS}
    base["EVENT_ID"] = kw.pop("EVENT_ID", "2027-thing-austin")
    base.update(kw)
    return base


# ----------------------------------------------------------- offering dead links --
DEAD = "https://example.com/gone/"


def test_dead_submission_link_is_flagged():
    out = brp.build([row(**{"SUBMISSION URL": DEAD})], dead_links={DEAD})
    assert out[0]["dead"] is True


def test_flag_follows_the_link_the_page_actually_offers():
    """The page prefers CFP_SUBMISSION_URL, so that is the one whose deadness matters.

    Testing whichever column happened to be convenient is how a page offers a dead link while
    reporting a live one as broken.
    """
    out = brp.build([row(**{"CFP_SUBMISSION_URL": DEAD, "SUBMISSION URL": "https://ok.com/x"})],
                    dead_links={DEAD})
    assert out[0]["dead"] is True
    assert out[0]["sub"] == DEAD

    out = brp.build([row(**{"CFP_SUBMISSION_URL": "https://ok.com/x", "SUBMISSION URL": DEAD})],
                    dead_links={DEAD})
    assert out[0]["dead"] is False, "flagged a column the page does not offer"


def test_a_known_dead_EVIDENCE_url_is_not_offered_as_live():
    """THE 2026-08-12 DEFECT.

    Decarb Connect North America carried DEADLINE_EVIDENCE_URL =
    decarbconnect.com/events/.../2026-speakers/, which link_checks had recorded dead since
    2026-08-09. Only the SUBMISSION URL was ever tested, so the page rendered "Where the
    deadline was read" as a working link to a 404, on a row labelled Verified and Open.

    The evidence flag is deliberately SEPARATE from `dead`: `dead` drives the "Submit Link
    Missing" badge, and an evidence problem is not a submission problem. Conflating them
    mislabels the row and sends the operator after the wrong fix.
    """
    out = brp.build([row(**{"DEADLINE_EVIDENCE_URL": DEAD, "SUBMISSION URL": "https://ok.com/x"})],
                    dead_links={DEAD})
    assert out[0]["evdead"] is True, "a URL we KNOW is dead was offered as evidence"
    assert out[0]["dead"] is False, "an evidence problem must not read as a missing submit link"


def test_a_live_evidence_url_is_left_alone():
    out = brp.build([row(**{"DEADLINE_EVIDENCE_URL": "https://ok.com/proof"})], dead_links={DEAD})
    assert out[0]["evdead"] is False


# ------------------------------------------------------------------- confidence --
def test_projected_is_carried_through_so_it_cannot_wear_a_verified_badge():
    """Contract 7: a projected date that looks confirmed is the most expensive thing here."""
    out = brp.build([row(**{"IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "Verified"})])
    assert out[0]["proj"] is True


def test_confidence_strips_the_parenthetical():
    out = brp.build([row(**{"GROUNDING_CONFIDENCE": "Verified (deep link)"})])
    assert out[0]["c"] == "Verified"


# --------------------------------------------------------------- edition states --
def test_an_event_that_has_run_is_watching_not_active():
    rows = [row(EVENT_ID="2026-thing-austin", **{"START DATE": "2026-01-01"})]
    assert brp.edition_states(rows, "2026-08-12")["2026-thing-austin"] == "Watching"


def test_a_later_edition_archives_the_earlier_one():
    rows = [row(EVENT_ID="2026-thing-austin", **{"START DATE": "2026-01-01"}),
            row(EVENT_ID="2027-thing-austin", **{"START DATE": "2027-01-01"})]
    st = brp.edition_states(rows, "2026-08-12")
    assert st["2026-thing-austin"] == "Archived"
    assert st["2027-thing-austin"] == "Active"


def test_a_rotating_event_is_not_a_dead_one():
    """EMO Hannover says it "will not be held in Hannover... the EMO cycle dictates". The
    series is alive, it just moves venue. Reading that as Discontinued retires a live event."""
    rows = [row(EVENT_ID="2027-emo-hannover", **{"START DATE": "2027-09-01",
                "STATUS DETAILS": "will not be held in Hannover; the EMO cycle dictates it "
                                  "moves to Milan"})]
    assert brp.edition_states(rows, "2026-08-12")["2027-emo-hannover"] != "Discontinued"


def test_genuinely_discontinued_is_caught():
    rows = [row(EVENT_ID="2027-gone-austin", **{"START DATE": "2027-09-01",
                "STATUS DETAILS": "the organisers have discontinued the event"})]
    assert brp.edition_states(rows, "2026-08-12")["2027-gone-austin"] == "Discontinued"


def test_rows_sharing_one_event_id_are_one_edition_in_several_markets():
    """CES reaches us once per market under a single EVENT_ID. Treating those as separate
    editions would archive one market's copy of a live conference."""
    rows = [row(EVENT_ID="2027-ces-las-vegas", Market="Robotics", **{"START DATE": "2027-01-06"}),
            row(EVENT_ID="2027-ces-las-vegas", Market="Semiconductor",
                **{"START DATE": "2027-01-06"})]
    st = brp.edition_states(rows, "2026-08-12")
    assert set(st.values()) == {"Active"}


# ------------------------------------------------------------------- dead links --
def test_load_dead_links_reads_the_submission_csv(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("CONFERENCE,SUBMISSION URL\nX," + DEAD + "\n", encoding="utf-8")
    assert brp.load_dead_links(str(p)) == {DEAD}


def test_load_dead_links_reads_a_plain_url_list(tmp_path):
    p = tmp_path / "d.txt"
    p.write_text(DEAD + "\nnot-a-url\n", encoding="utf-8")
    assert brp.load_dead_links(str(p)) == {DEAD}


def test_no_dead_links_file_means_none_known_not_none_dead():
    assert brp.load_dead_links(None) == set()


# ------------------------------------------------------------------------ checks --
def test_checks_are_keyed_by_event_id(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("EVENT_ID,CHECK,CHECK_URL,CHECK_QUOTE\n2027-thing-austin,verified,"
                 "https://ok.com/p,by 3 March\n", encoding="utf-8")
    out = brp.build([row()], checks=brp.load_checks(str(p)))
    assert out[0]["chk"] == "verified"
    assert out[0]["chkq"] == "by 3 March"


def test_a_row_with_no_check_gets_a_blank_not_a_guess():
    """2.6 - an honest blank. A missing verdict must never render as a verdict."""
    out = brp.build([row()], checks={})
    assert out[0]["chk"] == ""


@pytest.mark.parametrize("raw,shown", [("robotics", "Robotics"),
                                       ("ConsumerElectronics", "Consumer Electronics"),
                                       ("Whatever", "Whatever")])
def test_market_labels_are_humanised_without_losing_unknown_ones(raw, shown):
    assert brp.build([row(Market=raw)])[0]["m"] == shown
