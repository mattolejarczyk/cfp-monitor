"""scripts/refresh_plan.py: which awards are researched this week, and that the marks are safe and repeatable."""
import csv
from datetime import date

from scripts.refresh_plan import COLUMN, apply_marks, due, expected_open, plan, skipped_reasons, stable_hash

T = date(2026, 10, 9)


def rec(**k):
    base = {"status": "Closed", "deadline": "2026-03-01", "submission_opens": "2026-01-15", "source_as_of": "2026-09-30"}
    base.update(k)
    return base


def test_live_new_and_date_ahead_awards_are_always_researched():
    assert due(rec(status="Open"), "a", T) == (True, "live")
    assert due(rec(status="Needs Verification"), "a", T) == (True, "live")
    assert due(None, "a", T) == (True, "new") and due(rec(), "", T) == (True, "new")
    assert due(rec(deadline="2026-12-01"), "a", T) == (True, "date-ahead")           # a stale STATUS must not hide a date that is still ahead
    assert due(rec(submission_opens="2026-11-01"), "a", T) == (True, "date-ahead")


def test_a_closed_award_is_researched_when_its_next_cycle_should_be_opening():
    assert expected_open(rec(submission_opens="2026-01-15"), T).isoformat() == "2027-01-15"
    assert due(rec(submission_opens="2025-11-20", deadline="2026-02-01"), "a", T) == (True, "opening")     # last opened 20 Nov: due 20 Nov 2026, 42 days away
    assert expected_open(rec(submission_opens="", deadline="2026-02-01"), T).isoformat() == "2026-12-03"    # no opening date: deadline minus 60 days, moved a year


def test_a_dormant_closed_award_is_skipped_but_never_starved():
    r = rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of="2026-10-02")
    assert due(r, "x", T)[0] is False and due(r, "x", T)[1].startswith("dormant")
    assert due(rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of="2026-07-01"), "x", T) == (True, "stale")          # 100 days old
    assert due(rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of=""), "x", T) == (True, "stale")
    # rotation: over four consecutive weeks every closed award that is 21+ days old is researched exactly once
    from datetime import timedelta
    weeks = (date(2026, 10, 9), date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30))
    hits = [d for d in weeks if due(rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of=(d - timedelta(days=30)).isoformat()), "x", d) == (True, "rotation")]
    assert len(hits) == 1
    assert due(rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of=(T - timedelta(days=10)).isoformat()), "x", T)[0] is False      # researched 10 days ago: never due by rotation
    assert stable_hash("x") == stable_hash("x")


def test_plan_skips_nothing_when_it_would_skip_almost_everything_and_leaves_dup_rows_alone():
    rows = [{"CONFERENCE": f"A{i}", "EVENT_ID_CANON": f"id{i}", "DUP_OF": ""} for i in range(10)] + [{"CONFERENCE": "D", "EVENT_ID_CANON": "idd", "DUP_OF": "A1"}]
    db = {f"id{i}": rec(submission_opens="2026-04-01", deadline="2026-06-01", source_as_of="2026-10-05") for i in range(10)}
    pl = plan(rows, db, T, 0.7)
    assert pl["rows"] == 10 and pl["skip"] == {} and "skipping nothing" in pl["fuse"]
    assert len(plan(rows, db, T, 1.0)["skip"]) >= 8 and 10 not in plan(rows, db, T, 1.0)["skip"]          # the DUP_OF row is not this module's business


def test_marks_are_rewritten_not_accumulated_and_a_backup_is_kept(tmp_path):
    p = tmp_path / "Awards_input.csv"
    p.write_text('"CONFERENCE","EVENT_ID_CANON"\n"A","a"\n"B","b"\n', encoding="utf-8")
    assert apply_marks(p, {0: "dormant (closed)"}) == 1
    assert skipped_reasons(p) == ["dormant (closed): A"]
    assert apply_marks(p, {1: "dormant (closed)"}) == 1                       # the mark moves; the old one does not survive
    assert skipped_reasons(p) == ["dormant (closed): B"]
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert [r[COLUMN] for r in rows] == ["", "dormant (closed)"] and (tmp_path / "Awards_input.pre-refresh.csv").exists()
    assert skipped_reasons(tmp_path / "missing.csv") == []
