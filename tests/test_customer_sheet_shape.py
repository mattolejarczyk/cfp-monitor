"""The customer's sheet is reconciled against what we load, first, every time we download it.

Found 2026-09-16, the first time both sheets were compared column by column and value by value:

- COLUMNS reconciled cleanly (19 each, all mapped). But a renamed or removed column would have
  BLANKED that field on every row we hold: the loader wrote "" for a column it could not find.
- Arnica keeps organiser contact emails in SPEAKER & ABSTRACTS SUBMITTED, and any non-blank value
  was read as "already submitted" - six rows, it-sa among them, ranked as not worth working.
- "Needs Verification" was described as "date verified by their team".
- Two copies of their status vocabulary disagreed about "Closed".
"""
from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import clients, sheet_reconcile             # noqa: E402

_spec = importlib.util.spec_from_file_location("cc", ROOT / "scripts" / "customer_context.py")
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

FULL = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "EVENT START DATE", "LATEST UPDATE",
        "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS", "STATUS DETAILS",
        "SUBMISSION URL", "SPEAKER & ABSTRACTS SUBMITTED", "NOTIFICATION DATE", "OVERVIEW",
        "CATEGORIES", "COORDINATOR CONTACT INFO", "NOTES", "LOGIN", "PW"]


def _sheet(path, rows, headers=FULL):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})
    return path


def _db(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    clients.ensure_schema(con)
    return con


# --------------------------------------------------------------------------- structure --
def test_a_clean_sheet_reports_nothing_structural(tmp_path):
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [{"CONFERENCE": "A", "STATUS": "Submitted",
                                                         "PRIORITY": "High"}]))
    assert s["missing_fields"] == [] and s["unmapped_columns"] == [] and s["unrecognised"] == {}


def test_a_removed_column_is_named(tmp_path):
    heads = [h for h in FULL if h != "NOTES"]
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [{"CONFERENCE": "A"}], heads))
    assert s["missing_fields"] == ["notes"]


def test_a_removed_column_does_not_blank_what_we_hold(tmp_path):
    """THE ONE THAT MATTERS. Before this, deleting NOTES from their sheet would have erased every
    note in our client layer on the next load - and read as the customer clearing them."""
    con = _db(tmp_path)
    clients.load_sheet(con, "arnica", _sheet(tmp_path / "w1.csv",
                       [{"CONFERENCE": "Black Hat", "NOTES": "keynote in 2026", "STATUS": "Info Needed"}]),
                       industry="Cybersecurity")
    heads = [h for h in FULL if h != "NOTES"]
    s = clients.load_sheet(con, "arnica", _sheet(tmp_path / "w2.csv",
                           [{"CONFERENCE": "Black Hat", "STATUS": "Submitted"}], heads),
                           industry="Cybersecurity")
    notes, status = con.execute("select notes, status from client_conferences").fetchone()
    assert notes == "keynote in 2026", "a missing column must keep last week's value"
    assert status == "Submitted", "fields that ARE present still update"
    assert s["missing_fields_kept"] == ["notes"]


def test_a_new_column_is_reported(tmp_path):
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [{"CONFERENCE": "A"}], FULL + ["BUDGET"]))
    assert s["unmapped_columns"] == ["BUDGET"]


def test_a_repeated_conference_name_is_reported(tmp_path):
    """Name is the row identity. Two rows with one name means one silently overwrites the other."""
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [{"CONFERENCE": "RSA"}, {"CONFERENCE": "RSA"}]))
    assert s["duplicate_names"] == ["RSA"]


def test_credentials_are_counted_never_returned(tmp_path):
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv",
                                   [{"CONFERENCE": "A", "LOGIN": "someone", "PW": "hunter2"}]))
    assert s["credentials_filled"] == {"LOGIN": 1, "PW": 1}
    assert "hunter2" not in repr(s) and "someone" not in repr(s)


# ------------------------------------------------------------------------------ values --
def test_values_our_logic_does_not_understand_are_reported(tmp_path):
    """Both live on 2026-09-16: a note typed into STATUS, a priority typed into the verified column."""
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [
        {"CONFERENCE": "A", "STATUS": "2026 applications closed; monitor next cycle."},
        {"CONFERENCE": "B", "SUBMISSION DATE VERIFIED": "High"}]))
    assert "STATUS" in s["unrecognised"] and "SUBMISSION DATE VERIFIED" in s["unrecognised"]


def test_closed_is_recognised_but_not_classified(tmp_path):
    s = clients.sheet_shape(_sheet(tmp_path / "s.csv", [{"CONFERENCE": "A", "STATUS": "Closed"}]))
    assert s["undecided"] == {"Closed": 1} and "STATUS" not in s["unrecognised"]


def test_a_contact_email_is_not_a_submission():
    for v in ("events@owasp.com", "sponsors@labscon.io, info@labscon.io"):
        assert clients.is_contact_only(v) and not clients.records_a_submission(v)
    assert cc.bucket({"speaker_abstracts_submitted": "itsa365@nuernbergmesse.de"}) == "TRACKED"


def test_a_real_submission_record_still_counts():
    """The inversion: a name or an abstract title - or a name WITH an address - is a submission."""
    for v in ("Jane Doe - Securing AI code", "Yes", "jane@x.com and talk: AI supply chain"):
        assert clients.records_a_submission(v), v
    assert cc.bucket({"speaker_abstracts_submitted": "Jane Doe"}) == "MOOT"


def test_needs_verification_is_never_described_as_verified():
    assert "date verified" not in cc.describe({"submission_date_verified": "Needs Verification"})
    assert "date verified by their team" in cc.describe({"submission_date_verified": "Verified"})


# ------------------------------------------------------------------ one vocabulary --
def test_both_consumers_read_one_definition():
    assert cc.DONE is clients.DONE_STATES and cc.LIVE is clients.LIVE_STATES
    assert set(sheet_reconcile.SETTLED) - set(clients.DONE_STATES) == {"closed"}


def test_closed_keeps_each_consumers_old_behaviour_until_ruled():
    """Black Hat Asia and USENIX are 'Closed' with deadlines still ahead - so nothing reclassifies
    the word silently. The review page treated it as settled; the remediation tool did not."""
    assert sheet_reconcile.settled("Closed") is True
    assert cc.bucket({"status": "Closed"}) == "TRACKED"
