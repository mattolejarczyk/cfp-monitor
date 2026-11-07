"""One rule for "can this market's research be used?", shared by the Saturday import and the recap.

Born 2026-11-07 (docs/design/inspection-2026-11-07.md, defect 1). The research exit code was an unreliable
signal in both directions: Friday 2026-11-06 exited 1 (one stub row) for a run whose health was HEALTHY and
whose load was DONE, and the recap said FAILED; Saturday 2026-11-07's wrapper said exit 0 while both markets
exited 1. The signal is the run's own health verdict (<Market>_audited.health.json) and the row counts.
"""
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cfp_monitor import research_usable as ru                     # noqa: E402


def market(d: Path, name="Cybersecurity", inputs=(("A", "", ""), ("B", "", ""), ("C", "", "")),
           outputs=("A", "B", "C"), verdict="HEALTHY", reasons=(), health=True,
           output_age_h=0.0, health_age_h=0.0) -> Path:
    with open(d / f"{name}_input.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CONFERENCE", "DUP_OF", "REFRESH_SKIP"])
        w.writerows(inputs)
    out = d / f"{name}_audited.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["CONFERENCE"])
        w.writerows([[o] for o in outputs])
    if output_age_h:
        old = time.time() - output_age_h * 3600
        os.utime(out, (old, old))
    hp = d / f"{name}_audited.health.json"
    if health:
        hp.write_text(json.dumps({"verdict": verdict, "reasons": list(reasons), "call_health": {}, "grounding_trail": {}}),
                      encoding="utf-8")
        if health_age_h:
            old = time.time() - health_age_h * 3600
            os.utime(hp, (old, old))
    return d


def test_healthy_research_with_exit_1_is_usable(tmp_path):
    """Friday 2026-11-06: HEALTHY, one stub row, exit 1, load DONE. The recap said FAILED. It must say usable."""
    market(tmp_path)
    c = ru.check("Cybersecurity", tmp_path, research_exit=1)
    assert c.usable and c.why == "" and c.verdict == "HEALTHY"
    assert c.rows_out == 3 and c.rows_due == 3
    assert ru.check("Cybersecurity", tmp_path, research_exit=0).usable
    assert ru.check("Cybersecurity", tmp_path, research_exit=None).usable


def test_a_halt_exit_code_is_never_usable_whatever_the_verdict(tmp_path):
    market(tmp_path, verdict="HEALTHY")
    for code in (3, 4, 130, 2):
        c = ru.check("Cybersecurity", tmp_path, research_exit=code)
        assert not c.usable and f"exited {code}" in c.why, code


def test_a_failed_verdict_is_not_usable_and_the_reason_is_named(tmp_path):
    market(tmp_path, verdict="FAILED", reasons=["gemini_call: 40 of 50 failed (80%) - 40 http_504"])
    c = ru.check("Cybersecurity", tmp_path, research_exit=0)
    assert not c.usable and "FAILED" in c.why and "40 of 50 failed" in c.why


def test_a_degraded_verdict_is_usable_but_said_out_loud(tmp_path):
    """The row rule handles stub rows one by one; a DEGRADED run is loadable, and the recap must say DEGRADED, not WORKED quietly."""
    market(tmp_path, verdict="DEGRADED", reasons=["grounding: 3 of 20 answers had NO SEARCH RAN"])
    c = ru.check("Cybersecurity", tmp_path, research_exit=1)
    assert c.usable and c.verdict == "DEGRADED"
    assert any("DEGRADED" in n and "NO SEARCH RAN" in n for n in c.notes)


def test_a_short_run_is_not_usable_and_skipped_rows_are_not_counted_as_due(tmp_path):
    market(tmp_path, inputs=(("A", "", ""), ("B", "", "dormant (closed)"), ("C", "x", ""), ("D", "", "")), outputs=("A", "D"))
    c = ru.check("Cybersecurity", tmp_path, research_exit=1)
    assert c.usable and c.rows_due == 2 and c.rows_out == 2
    market(tmp_path, inputs=(("A", "", ""), ("B", "", ""), ("D", "", "")), outputs=("A", "D"))
    c = ru.check("Cybersecurity", tmp_path, research_exit=1)
    assert not c.usable and "stopped short" in c.why and "2 rows for 3" in c.why


def test_missing_or_stale_output_is_not_usable(tmp_path):
    c = ru.check("Utility", tmp_path, research_exit=0)
    assert not c.usable and "no research output" in c.why
    market(tmp_path, name="Utility", output_age_h=ru.MAX_OUTPUT_AGE_H + 5)
    c = ru.check("Utility", tmp_path, research_exit=0)
    assert not c.usable and "old" in c.why


def test_no_health_verdict_is_said_and_the_row_count_decides(tmp_path):
    """A run that died before writing its verdict: the rows decide, and the absence is noted, never hidden."""
    market(tmp_path, health=False)
    c = ru.check("Cybersecurity", tmp_path, research_exit=0)
    assert c.usable and c.verdict is None and any("no health verdict" in n for n in c.notes)
    # a verdict file from a previous week is not this run's verdict
    market(tmp_path, verdict="HEALTHY", health_age_h=ru.MAX_OUTPUT_AGE_H + 5)
    c = ru.check("Cybersecurity", tmp_path, research_exit=0)
    assert c.verdict is None and any("no health verdict" in n for n in c.notes)


def test_the_import_asks_the_shared_rule(tmp_path):
    """weekend_import.check_research is the shared rule, not a second opinion: same fixture, same answer, in both directions."""
    from scripts.weekend_import import check_research
    market(tmp_path, verdict="HEALTHY")
    assert check_research("Cybersecurity", tmp_path, 1) is None
    market(tmp_path, verdict="FAILED", reasons=["gemini_call: every call failed"])
    why = check_research("Cybersecurity", tmp_path, 1)
    assert why == ru.check("Cybersecurity", tmp_path, 1).why and "FAILED" in why


LOG = ("INTAKE HEALTH: ok\n"
       "=== OVERNIGHT RUN 20261106-020456 ===\n"
       "Market : {market}\n"
       "Rows read: 3 | already in file: 0 | skipped (already done): 0 | attempted: 3 | written: 3 | in output file: 3 (expected 3)\n"
       "API requests spent this run: 4 (paced at 1 per 16s, retries included)\n"
       "RUN HEALTH: HEALTHY\n"
       "GROUNDING TRAIL: 3 rows | 3 grounded, 0 no-search | 1 citation-host-not-in-sources (A)\n"
       "=== run_monthly exit code: {exit} ===\n")


def test_the_recap_subject_reads_worked_for_a_healthy_exit_1_run_whose_load_was_done(tmp_path):
    """The Friday 2026-11-06 shape: research HEALTHY, exit 1, import DONE. Subject: WORKED."""
    from scripts.weekend_recap import saturday_recap
    market(tmp_path, name="Awards", verdict="HEALTHY")
    imp = {"status": "DONE", "database": "updated",
           "markets": [{"market": "Awards", "status": "PROMOTED", "from_this_week": 2, "from_last_week": 1, "held_back": 0}]}
    subject, text, _ = saturday_recap(LOG.format(market="Awards", exit=1), imp, tmp_path, "friday", None)
    assert "Friday awards research WORKED" in subject, subject
    assert "Research usable" in text and "HEALTHY" in text


def test_the_recap_says_failed_when_the_health_verdict_is_failed_even_on_exit_0(tmp_path):
    """The other direction: the Saturday 2026-11-07 wrapper reported exit 0 whatever the markets did. Exit 0 proves nothing."""
    from scripts.weekend_recap import saturday_recap
    market(tmp_path, name="Cybersecurity", verdict="FAILED", reasons=["gemini_call: 50 of 50 failed"])
    imp = {"status": "FAILED", "database": "unchanged", "markets": [{"market": "Cybersecurity", "status": "FAILED", "why": "x"}]}
    subject, text, _ = saturday_recap(LOG.format(market="Cybersecurity", exit=0), imp, tmp_path, "saturday", None)
    assert "Saturday research FAILED" in subject, subject
    assert "50 of 50 failed" in text


def test_the_monthly_recap_uses_the_same_rule(tmp_path):
    from scripts.weekend_recap import monthly_recap
    market(tmp_path, name="Robotics", verdict="HEALTHY")
    subject, text, _ = monthly_recap(LOG.format(market="Robotics", exit=1), tmp_path)
    assert "WORKED" in subject, subject
    market(tmp_path, name="Robotics", verdict="FAILED", reasons=["gemini_call: every call failed"])
    subject, text, _ = monthly_recap(LOG.format(market="Robotics", exit=0), tmp_path)
    assert "FAILED" in subject, subject
