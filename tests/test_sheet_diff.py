"""Week-over-week on a client's sheet: what they acted on, and where silence costs something.

The customer maintains their list by hand. Their edits are the most reliable data in the system.
Their INACTION is usually fine - nobody works every row every week - and reporting all of it
would train the reader to skip the report, which is exactly how the weekly digest failed before
the NEW-vs-STANDING split.
"""
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import sheet_diff              # noqa: E402

TODAY = date(2026, 8, 31)
COLS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "EVENT START DATE", "LATEST UPDATE",
        "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS",
        "STATUS DETAILS", "SUBMISSION URL", "SPEAKER & ABSTRACTS SUBMITTED", "NOTES"]


def _row(name, **kw):
    d = dict.fromkeys(COLS, "")
    d["CONFERENCE"] = name
    d.update({k.replace("_", " ").upper(): v for k, v in kw.items()})
    return d


def _sheet(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return path


def _diff(tmp, before_rows, after_rows, today=TODAY):
    b = _sheet(tmp / "b.csv", before_rows)
    a = _sheet(tmp / "a.csv", after_rows)
    return sheet_diff.diff(b, a, today)


def test_a_customer_edit_counts_as_acting(tmp_path):
    d = _diff(tmp_path, [_row("Black Hat", STATUS="")],
              [_row("Black Hat", STATUS="Submitted")])
    assert len(d["acted"]) == 1
    assert d["acted"][0]["changes"] == [("STATUS", "", "Submitted")]


def test_our_own_correction_is_not_them_acting(tmp_path):
    """Counting a deadline WE fixed as customer engagement would tell us they are working the
    sheet when they have not opened it."""
    d = _diff(tmp_path, [_row("Black Hat", SUBMISSION_DEADLINE="2026-11-01")],
              [_row("Black Hat", SUBMISSION_DEADLINE="2026-11-15")])
    assert d["acted"] == []
    assert len(d["corrected"]) == 1


def test_latest_update_moving_is_never_evidence_of_anything(tmp_path):
    """It moves in bulk - many Utility rows share one value - so it cannot mean a row was
    worked."""
    d = _diff(tmp_path, [_row("Black Hat", LATEST_UPDATE="2026-06-15")],
              [_row("Black Hat", LATEST_UPDATE="2026-08-30")])
    assert d["acted"] == [] and d["corrected"] == [] and d["untouched"] == 1


def test_a_verification_request_is_its_own_category(tmp_path):
    d = _diff(tmp_path, [_row("Black Hat", SUBMISSION_DATE_VERIFIED="")],
              [_row("Black Hat", SUBMISSION_DATE_VERIFIED="Needs Verification")])
    assert len(d["requested"]) == 1 and d["acted"] == []


def test_added_and_removed_rows_are_reported_separately(tmp_path):
    d = _diff(tmp_path, [_row("Black Hat"), _row("BSides")],
              [_row("Black Hat"), _row("KubeCon")])
    assert d["added"] == ["KubeCon"] and d["removed"] == ["BSides"]


def test_untouched_is_counted_not_listed(tmp_path):
    """53 untouched rows every week is noise. The count is the signal."""
    rows = [_row(f"Conf {i}") for i in range(20)]
    d = _diff(tmp_path, rows, rows)
    assert d["untouched"] == 20
    report = sheet_diff.render(d, "arnica", TODAY)
    assert "Untouched: 20 row(s)" in report
    assert "Conf 7" not in report, "untouched rows must not be listed one by one"


def test_silence_on_a_row_closing_soon_IS_reported(tmp_path):
    """The safety net. Untouched, no status, deadline inside 30 days - a submission they may
    be about to miss."""
    rows = [_row("Closing Soon", SUBMISSION_DEADLINE="2026-09-05")]
    d = _diff(tmp_path, rows, rows)
    assert len(d["at_risk"]) == 1
    a = d["at_risk"][0]
    assert a["days"] == 5 and a["band"] == "closing this week"
    assert "NOT ACTED ON AND CLOSING SOON" in sheet_diff.render(d, "arnica", TODAY)


def test_a_row_still_being_drafted_IS_at_risk(tmp_path):
    """The real Utility sheet on 2026-08-31: H2 MEET's deadline was that day with status
    'Drafting Abstract', and CES 2027 was nine days out on 'Info Needed'. Work started but not
    finished, or blocked waiting on someone, is exactly the row that gets missed."""
    for status in ("Drafting Abstract", "Info Needed"):
        rows = [_row("In Progress", SUBMISSION_DEADLINE="2026-09-05", STATUS=status)]
        d = _diff(tmp_path, rows, rows)
        assert len(d["at_risk"]) == 1, f"{status} must still be flagged"
        assert d["at_risk"][0]["status"] == status


def test_the_safety_net_describes_itself_accurately(tmp_path):
    """It said 'no status set' while flagging rows whose status was 'Drafting Abstract'. A
    report that misdescribes its own contents is the defect this project keeps finding."""
    rows = [_row("Drafting", SUBMISSION_DEADLINE="2026-09-05", STATUS="Drafting Abstract")]
    report = sheet_diff.render(_diff(tmp_path, rows, rows), "utility-global", TODAY)
    assert "no status set" not in report
    assert "not yet in a settled state" in report
    assert "Drafting Abstract" in report, "their status belongs in the table"


def test_a_row_they_already_dealt_with_is_not_at_risk(tmp_path):
    """Silence after 'Submitted' is correct, not a warning. Flagging it would make the safety
    net cry wolf on exactly the rows that went well."""
    for status in ("Submitted", "Accepted", "Closed", "Not Appropriate", "Client Declined"):
        rows = [_row("Done", SUBMISSION_DEADLINE="2026-09-05", STATUS=status)]
        d = _diff(tmp_path, rows, rows)
        assert d["at_risk"] == [], f"{status} should not be at risk"


def test_a_passed_deadline_is_not_at_risk(tmp_path):
    rows = [_row("Gone", SUBMISSION_DEADLINE="2026-06-01")]
    assert _diff(tmp_path, rows, rows)["at_risk"] == []


def test_a_distant_deadline_is_not_at_risk(tmp_path):
    rows = [_row("Later", SUBMISSION_DEADLINE="2027-06-01")]
    assert _diff(tmp_path, rows, rows)["at_risk"] == []


def test_prose_in_the_deadline_column_does_not_become_a_number(tmp_path):
    """Their deadline column also carries 'Call opens... closes... (UTC+02:00)' and
    'Sponsorship Required - $12,500'. A date invented from prose is worse than no date."""
    for junk in ("Call opens: 01/01/2026 12:00 AM, closes: 03/01/2026 11:59 PM",
                 "Sponsorship Required - $12,500", "TBD", ""):
        rows = [_row("Prose", SUBMISSION_DEADLINE=junk)]
        d = _diff(tmp_path, rows, rows)
        assert d["at_risk"] == [], f"invented urgency from {junk!r}"


def test_us_slash_dates_are_read_the_way_they_write_them(tmp_path):
    """Their sheets use MM/DD/YYYY throughout."""
    rows = [_row("US Format", SUBMISSION_DEADLINE="09/05/2026")]
    d = _diff(tmp_path, rows, rows)
    assert len(d["at_risk"]) == 1 and d["at_risk"][0]["days"] == 5


def test_a_quiet_week_says_so_plainly(tmp_path):
    rows = [_row("A"), _row("B")]
    report = sheet_diff.render(_diff(tmp_path, rows, rows), "arnica", TODAY)
    assert "No change since the last snapshot" in report
    assert "normal week" in report
    assert "safety net is clear" in report


def test_the_report_names_who_acts_on_each_category(tmp_path):
    d = _diff(tmp_path, [_row("A", STATUS=""), _row("B", SUBMISSION_DATE_VERIFIED="")],
              [_row("A", STATUS="Submitted"), _row("B", SUBMISSION_DATE_VERIFIED="Needs Verification")])
    report = sheet_diff.render(d, "arnica", TODAY)
    assert "Who acts" in report and "**Us**, this week" in report
    assert "Never overwrite" in report
