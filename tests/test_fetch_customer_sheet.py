"""The customer-sheet intake keeps its evidence and tolerates a blank first header cell (2026-11-07, inspection defect 3).

On 2026-11-07 the Utility Global sheet's export came back with cell A1 blank (a run of spaces where CONFERENCE was); every
other column and all 84 rows were intact. validate() refused it with "missing column CONFERENCE ... check the gid" and threw the
export away ("Nothing was saved"), so the cause could only be found by fetching again. Quality by design rule 2: every failure
keeps its evidence at the moment it happens.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import fetch_customer_sheet as fcs                        # noqa: E402

GOOD = ('CONFERENCE,SUBMISSION DEADLINE,STATUS,NOTES\r\n'
        '"Sustainable Aviation Futures (MENA)",2026-12-01,Info Needed,"keep, this"\r\n'
        'Gastech 2027,2027-02-01,Submitted,\r\n')
BLANK_A1 = GOOD.replace("CONFERENCE,", "   ,", 1)


def test_a_good_sheet_survives_untouched(tmp_path):
    rows, text, note = fcs.validate(GOOD, "utility", evidence_dir=tmp_path)
    assert rows == 2 and text == GOOD and note is None
    assert not list(tmp_path.iterdir()), "nothing to keep when nothing failed"


def test_a_blank_first_header_cell_is_mapped_to_conference_and_said(tmp_path):
    """The 2026-11-07 Utility export: A1 blank, everything else present."""
    rows, text, note = fcs.validate(BLANK_A1, "utility", evidence_dir=tmp_path)
    assert rows == 2
    assert text.split("\r\n", 1)[0] == "CONFERENCE,SUBMISSION DEADLINE,STATUS,NOTES"
    assert text.split("\r\n", 1)[1] == GOOD.split("\r\n", 1)[1], "the data rows are byte for byte the export's"
    assert note and "A1" in note and "CONFERENCE" in note
    assert not list(tmp_path.iterdir()), "a mapped header is not a failure: no evidence file"


def test_a_blank_first_header_cell_with_another_column_missing_is_refused_as_header_cell_blank(tmp_path):
    text = BLANK_A1.replace("SUBMISSION DEADLINE", "DEADLINE")
    with pytest.raises(RuntimeError) as e:
        fcs.validate(text, "utility", evidence_dir=tmp_path)
    msg = str(e.value)
    assert "header cell blank" in msg and "check the gid" not in msg
    kept = tmp_path / "intake_failed_utility.csv"
    assert kept.exists() and kept.read_bytes().decode("utf-8") == text
    assert str(kept) in msg, "the error names the evidence file"
    assert "Nothing was saved" not in msg


def test_a_named_first_header_with_a_column_missing_keeps_the_gid_hint_and_the_evidence(tmp_path):
    text = GOOD.replace("STATUS", "STATE")
    with pytest.raises(RuntimeError) as e:
        fcs.validate(text, "arnica", evidence_dir=tmp_path)
    msg = str(e.value)
    assert "check the gid" in msg and "STATUS" in msg and "header cell blank" not in msg
    kept = tmp_path / "intake_failed_arnica.csv"
    assert kept.exists() and kept.read_bytes().decode("utf-8") == text and str(kept) in msg


def test_an_export_with_no_rows_keeps_its_evidence_too(tmp_path):
    text = GOOD.split("\r\n", 1)[0] + "\r\n"
    with pytest.raises(RuntimeError) as e:
        fcs.validate(text, "utility", evidence_dir=tmp_path)
    assert "no rows" in str(e.value) and str(tmp_path / "intake_failed_utility.csv") in str(e.value)
    assert (tmp_path / "intake_failed_utility.csv").read_bytes().decode("utf-8") == text


def test_an_awards_sheet_with_a_blank_first_cell_is_still_refused(tmp_path):
    """The mapping is for CONFERENCE only (the case seen); an awards sheet keying on AWARD is refused, and told why."""
    text = "   ,SUBMISSION DEADLINE,STATUS\r\nAlpha Prize,2027-01-01,Open\r\n"
    with pytest.raises(RuntimeError) as e:
        fcs.validate(text, "arnica-awards", kind="awards", evidence_dir=tmp_path)
    assert "AWARD" in str(e.value) and "header cell blank" in str(e.value)
    assert (tmp_path / "intake_failed_arnica-awards.csv").exists()
