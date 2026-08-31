"""The decision tree. Where a conference sits in its life, and what follows for both sides.

Written 2026-08-31 after the gate failed on two rows reading STATUS=Open whose deadlines had
passed within 48 hours. Neither needed research; they needed deriving. Judgement rule 5 already
said "a stored judgement goes stale; derive it instead" - this makes it executable.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import lifecycle              # noqa: E402

TODAY = date(2026, 8, 31)


def _row(eid="2026-someconf-boston", start="", deadline="", details="", notes=""):
    return {"EVENT_ID": eid, "START DATE": start, "SUBMISSION DEADLINE": deadline,
            "STATUS DETAILS": details, "NOTES": notes}


def A(row, state="Active"):
    return lifecycle.assess(row, state, TODAY)


# ------------------------------------------------------- the customer-visible answer

def test_a_passed_deadline_is_never_reported_as_open():
    """THE 2026-08-31 FAILURE. SecureWorld New York City held STATUS=Open with a deadline of
    2026-08-29, and European Biomethane Week with 2026-08-30. Both passed within 48 hours."""
    a = A(_row(start="2026-11-01", deadline="2026-08-29"))
    assert a.call_state == "Closed"
    assert a.customer_status == "Closed"
    assert a.urgency == "none"
    assert "2 day(s) ago" in a.why


def test_a_call_closing_this_week_outranks_everything():
    a = A(_row(start="2026-12-01", deadline="2026-09-04"))
    assert a.urgency == "closing this week"
    assert a.customer_status == "Open"
    assert "costs the customer a submission" in a.why


def test_a_call_closing_this_month_is_surfaced_but_not_alarming():
    a = A(_row(start="2026-12-01", deadline="2026-09-20"))
    assert a.urgency == "closing this month"


def test_a_distant_call_is_open_and_quiet():
    a = A(_row(start="2027-06-01", deadline="2027-01-15"))
    assert a.urgency == "open" and a.customer_status == "Open"
    assert a.cost == "free", "watching a distant deadline costs nothing"


# ------------------------------------------------------- what WE do, and what it costs

def test_a_conference_that_just_ran_asks_almost_nothing_of_anyone():
    """The case Matt described: it happened last week, the next one is a year out, so the
    customer needs nothing for months - but we quietly move it to watching."""
    a = A(_row(start="2026-08-24"), state="Watching")
    assert a.edition_state == "Watching"
    assert a.urgency == "none"
    assert a.cost == "free"
    assert "do not hunt the successor yet" in a.action
    assert "spends requests to be told nothing" in a.why


def test_after_the_quiet_window_we_start_looking_for_the_successor():
    a = A(_row(start="2026-05-01"), state="Watching")
    assert a.cost == "quota"
    assert "successor" in a.action and "R14" in a.action


def test_a_past_event_is_never_sent_looking_for_its_own_call():
    """Judgement rule 1, 2026-08-11: 11 of 93 grounded requests were spent hunting CFP pages
    for conferences that had already taken place."""
    for state in ("Watching", "Archived", "Discontinued"):
        a = A(_row(start="2026-01-01", deadline=""), state=state)
        assert "find the call" not in a.action, f"{state} must not trigger discovery"


def test_a_discontinued_series_is_never_researched_again():
    a = A(_row(), state="Discontinued")
    assert a.cost == "free" and "do not spend a request" in a.action
    assert a.customer_status == "Closed"


def test_an_archived_edition_defers_to_its_successor():
    a = A(_row(), state="Archived")
    assert a.cost == "free" and "successor edition carries the work" in a.action


def test_a_future_event_with_no_deadline_is_DISCOVERY_not_verification():
    """The 24 rows in the customer's Needs Verification queue that we hold with no deadline.
    Verification cannot help - there is no claim to check."""
    a = A(_row(start="2027-03-01", deadline=""))
    assert a.call_state == "Not announced"
    assert a.cost == "quota"
    assert "DISCOVERY, not verification" in a.action
    assert "no claim to check" in a.why


def test_prose_in_the_deadline_field_asks_for_a_human_not_a_guess():
    """'Call opens... closes... (UTC+02:00)' and 'Sponsorship Required - $12,500' both live in
    that column. A date invented from prose is worse than no date."""
    a = A(_row(start="2027-03-01",
               deadline="Call opens: 01/01/2026, closes: 03/01/2026 11:59 PM (UTC+02:00)"))
    assert a.cost == "human"
    assert "not a date" in a.why and "R23" in a.why


# ------------------------------------------------------- structural

def test_every_assessment_gives_a_reason():
    """A decision without a reason becomes a rule nobody dares change and nobody understands."""
    cases = [(_row(start="2026-11-01", deadline="2026-08-01"), "Active"),
             (_row(start="2026-11-01", deadline="2026-09-02"), "Active"),
             (_row(start="2027-01-01", deadline=""), "Active"),
             (_row(start="2026-08-24"), "Watching"),
             (_row(), "Archived"), (_row(), "Discontinued")]
    for row, state in cases:
        a = lifecycle.assess(row, state, TODAY)
        assert a.why and len(a.why) > 30, f"{state} has no real reason"
        assert a.action and a.cost in ("free", "quota", "human")


def test_edition_state_groups_by_event_id_before_series():
    """Rows sharing one EVENT_ID are ONE edition in several markets. Getting this backwards
    produced advice to merge 12 rows of correct data."""
    rows = [{"EVENT_ID": "2026-ces-lasvegas", "START DATE": "2026-01-06",
             "STATUS DETAILS": "", "NOTES": ""},
            {"EVENT_ID": "2026-ces-lasvegas", "START DATE": "2026-01-06",
             "STATUS DETAILS": "", "NOTES": ""},
            {"EVENT_ID": "2027-ces-lasvegas", "START DATE": "2027-01-05",
             "STATUS DETAILS": "", "NOTES": ""}]
    st = lifecycle.edition_states(rows, TODAY)
    assert st["2026-ces-lasvegas"] == "Archived", "a later edition exists"
    assert st["2027-ces-lasvegas"] == "Active"


def test_a_rotating_event_is_not_a_dead_one():
    """EMO Hannover 2027: 'will not be held in Hannover... the EMO cycle dictates'. The series
    is alive, it has moved venue."""
    rows = [{"EVENT_ID": "2027-emo-hannover", "START DATE": "2027-09-01",
             "STATUS DETAILS": "will not be held in Hannover, the EMO cycle dictates",
             "NOTES": ""}]
    assert lifecycle.edition_states(rows, TODAY)["2027-emo-hannover"] == "Active"


def test_the_page_builder_uses_this_module_rather_than_its_own_copy():
    """It had its own edition_states, which is why the gate and the weekly job could not ask
    the question - and why STATUS went on being read from the file."""
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "from src.cfp_monitor.lifecycle import edition_states" in src
    assert "def edition_states(" not in src, "a second implementation has reappeared"
