"""ACT-26: the share of events that needed a manual verification, by month (failure point F3). Definition in board_metrics.manual_verification_share."""
import json

from scripts import board_metrics as bm

LOG = """# Operator-ruled edits

## 2026-10-01 11:38 - Global Energy Show Canada 2027, submission link
- Event: `2027-ges-calgary`. The operator confirmed on the live page that the button links here.

## 2026-10-03 - ODSC East
- Event `2027-odsc-boston`. The research returned a start date and I cleared it (not a verification).

## 2026-10-03 (later) - CORRECTION: ODSC East 2027 was a correct date
- The pin 'operator verified' was wrong. `2027-odsc-boston` restored. The operator ruled nothing.

## 2026-10-05 - nine rows stamped with ids
- Upstream confirmed ids; `2027-ges-calgary` and `2027-other` stamped.

## 2026-11-02 - something verified in November
- The operator verified the page for `2027-other` by hand.
"""
ROSTER = {"2027-ges-calgary", "2027-odsc-boston", "2027-other", "2027-a", "2027-b"}
PINS = [{"canonical": "2027-a", "ruled_on": "2026-10-03"}, {"canonical": "2027-b", "ruled_on": "2026-10-04"}, {"canonical": "2027-a", "ruled_on": "2026-10-04"}]


def test_log_counts_only_entries_where_the_operator_verified_or_ruled_and_not_corrections():
    ev = bm.edits_log_events(LOG, ROSTER)
    assert ev == [("2026-10", "2027-ges-calgary"), ("2026-11", "2027-other")]      # identity stamping, a repair note and a CORRECTION entry are not verifications


def test_share_is_distinct_events_over_the_roster_per_month():
    s = bm.manual_verification_share(PINS, LOG, ROSTER, "2026-11-10")
    by = {m["month"]: m for m in s["months"]}
    assert by["2026-10"]["events"] == 3 and by["2026-10"]["share_pct"] == 60.0       # 2027-a (pinned twice), 2027-b, 2027-ges-calgary
    assert by["2026-11"]["events"] == 1 and by["2026-11"]["partial"] is True and by["2026-11"]["share_pct"] == 20.0
    assert by["2026-10"]["partial"] is False and s["roster"] == 5
    assert "estimate" in s["definition"]


def test_no_record_means_no_month_not_a_zero():
    assert bm.manual_verification_share([], "", ROSTER, "2026-10-05")["months"] == []


def test_the_status_file_gets_only_the_manual_verification_key(tmp_path):
    p = tmp_path / "status.json"
    p.write_text(json.dumps({"quality": {"conference": {"x": 1}}, "headline": {"a": 1}}), encoding="utf-8")
    s = bm.manual_verification_share(PINS, LOG, ROSTER, "2026-10-05")
    bm.update_manual_status(s, "2026-10-05", p)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["quality"]["conference"] == {"x": 1} and d["headline"] == {"a": 1}
    assert d["quality"]["manual_verification"]["months"][0]["month"] == "2026-10" and d["quality"]["manual_verification"]["roster"] == 5


def test_the_real_ledger_and_log_give_a_first_month():
    from scripts.pinned_rows import load_pins
    s = bm.manual_verification_share(load_pins(), bm.EDITS_LOG.read_text(encoding="utf-8"), {p["canonical"] for p in load_pins()} | {"x" * 3}, "2026-10-05")
    assert s["months"] and s["months"][0]["month"] == "2026-10" and s["months"][0]["events"] >= 15
