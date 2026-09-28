"""WEEKEND-PROCESS.md must be re-confirmed whenever a script it describes changes (2026-09-28).

If this fails: read the listed scripts, correct docs/operations/WEEKEND-PROCESS.md in plain
English, then run `python scripts/check_process_doc.py --confirm`. Never re-stamp unread.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_process_doc as cpd  # noqa: E402


def test_weekend_process_doc_matches_its_scripts():
    stale = cpd.changed()
    assert not stale, (
        "WEEKEND-PROCESS.md may no longer describe the weekend process - these scripts changed "
        f"since it was confirmed: {stale}. Update the document, then run "
        "scripts/check_process_doc.py --confirm.")


def test_every_described_script_is_named_in_the_document():
    text = cpd.DOC.read_text(encoding="utf-8")
    for key in cpd.DESCRIBED:
        assert Path(key).name in text, f"{key} is fingerprinted but never mentioned in the document"
