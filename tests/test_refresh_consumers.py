"""ACT-33: everything downstream of the research that assumed ALL rows were researched, proven to handle rows the refresh policy skipped (REFRESH_SKIP).
The checklist is in docs/operations/QA-REGISTER.md (A60) and the rehearsal evidence is in the ACT-33 hand-over; this file is the part that runs offline every time.
Tests that read the live Markets scripts (run_canary.ps1, validate_market_output.py) skip themselves when those files are absent (a clean checkout)."""
import csv
import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")

COLS = ["CONFERENCE", "STATUS", "EVENT_ID_CANON", "DUP_OF", "REFRESH_SKIP"]


def write_input(path: Path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in COLS} for r in rows])


ROWS = [{"CONFERENCE": "Dormant One", "EVENT_ID_CANON": "d1", "REFRESH_SKIP": "G2 dormant: closed"},
        {"CONFERENCE": "Dormant Two", "EVENT_ID_CANON": "d2", "REFRESH_SKIP": "G3 dormant: closed"},
        {"CONFERENCE": "Live One", "EVENT_ID_CANON": "l1"},
        {"CONFERENCE": "Live Two", "EVENT_ID_CANON": "l2"},
        {"CONFERENCE": "Dup", "EVENT_ID_CANON": "x", "DUP_OF": "Live One"}]


# ---- Markets/run_canary.ps1: samples only rows that WILL be researched (fixed 2026-10-09 for awards; proven here on a conference input)
@pytest.mark.skipif(not (MARKETS / "run_canary.ps1").exists(), reason="live Markets folder not present")
def test_canary_samples_only_non_skipped_rows_of_a_conference_input(tmp_path):
    text = (MARKETS / "run_canary.ps1").read_text(encoding="utf-8")
    m = re.search(r"^\$all = @\(\$all \| Where-Object \{.*REFRESH_SKIP.*\}\)\s*$", text, re.M)
    assert m, "the canary no longer filters REFRESH_SKIP rows"
    inp = tmp_path / "Cybersecurity_input.csv"
    write_input(inp, ROWS[:4] + [{"CONFERENCE": "Dormant Three", "EVENT_ID_CANON": "d3", "REFRESH_SKIP": "G4 dormant"}] * 0)
    script = tmp_path / "t.ps1"
    script.write_text(f"$all = Import-Csv '{inp}'\n{m.group(0)}\n$all | ForEach-Object {{ $_.CONFERENCE }}\n", encoding="utf-8")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=120).stdout.split()
    assert out == ["Live", "One", "Live", "Two"]                                                            # the two dormant rows are never sampled
    # an input WITHOUT the column (every market before the policy) is unaffected
    inp2 = tmp_path / "plain.csv"
    inp2.write_text('"CONFERENCE","EVENT_ID_CANON"\n"A","a"\n"B","b"\n', encoding="utf-8")
    script.write_text(f"$all = Import-Csv '{inp2}'\n{m.group(0)}\n$all | ForEach-Object {{ $_.CONFERENCE }}\n", encoding="utf-8")
    assert subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=120).stdout.split() == ["A", "B"]


# ---- Markets/validate_market_output.py check_coverage: a skipped row is not 'lost'
class _Report:
    def __init__(self):
        self.errors, self.warns = [], []

    def error(self, *a):
        self.errors.append(a)

    def warn(self, *a):
        self.warns.append(a)


@pytest.mark.skipif(not (MARKETS / "validate_market_output.py").exists(), reason="live Markets folder not present")
def test_validator_coverage_does_not_call_a_skipped_row_lost(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("vmo", MARKETS / "validate_market_output.py")
    vmo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vmo)
    inp = tmp_path / "in.csv"
    write_input(inp, ROWS)
    out_rows = [{"CONFERENCE": "Live One"}, {"CONFERENCE": "Live Two"}]
    rep = _Report()
    vmo.check_coverage(out_rows, str(inp), rep)
    assert rep.errors == [] and rep.warns == []
    rep = _Report()                                                                                          # a genuinely truncated run is still loud
    vmo.check_coverage([{"CONFERENCE": "Live One"}], str(inp), rep)
    assert rep.errors and "Live Two" in str(rep.errors)


# ---- scripts/weekend_import.py: n_in excludes REFRESH_SKIP (and DUP_OF), so a short file is only 'short' against the rows that were due
def test_weekend_import_does_not_call_a_policy_skip_a_short_run(tmp_path):
    from scripts.weekend_import import check_research
    write_input(tmp_path / "Cybersecurity_input.csv", ROWS)
    out = tmp_path / "Cybersecurity_audited.csv"
    out.write_text('"CONFERENCE"\n"Live One"\n"Live Two"\n', encoding="utf-8")
    assert check_research("Cybersecurity", tmp_path, 0) is None                                              # 2 rows for 2 due rows
    out.write_text('"CONFERENCE"\n"Live One"\n', encoding="utf-8")
    assert "holds 1 rows for 2 input rows" in check_research("Cybersecurity", tmp_path, 0)                   # still catches a truncated run
    # an audit file older than 30 hours is still refused whatever is skipped
    old = time.time() - 40 * 3600
    os.utime(out, (old, old))
    assert "h old" in check_research("Cybersecurity", tmp_path, 0)


# ---- the carry-over of last week's row and the step counts: a skipped row is COVERAGE, never FIND/PROVE/READ, and COVERAGE never raises the 'rises' flag
def test_a_carried_over_row_is_counted_as_coverage_and_never_as_a_failure():
    from scripts import failure_steps as fs
    decisions = [{"action": "carried-over", "reasons": ["not covered by this week's research"], "conference": f"c{i}"} for i in range(25)]
    summ = fs.summarize(decisions)
    cnt = fs.counts(summ)
    assert cnt["COVERAGE"] == 25 and cnt["READ"] == cnt["FIND"] == cnt["PROVE"] == 0
    assert fs.rises(cnt, {"COVERAGE": 0}) == []                                                              # 25 more skipped than last week is not a flag
    assert fs.line(cnt) == "none"


# ---- scripts/customer_coverage.py: a skipped row is still in the research queue
def test_customer_coverage_counts_a_policy_skipped_row_as_in_the_queue():
    from scripts import customer_coverage as cc
    inputs = {"Cybersecurity": [{"CONFERENCE": "Dormant One", "EVENT_ID_CANON": "d1", "CONFERENCE URL": "https://d1.example/", "START DATE": "2026-09-01", "REFRESH_SKIP": "G2 dormant"},
                                {"CONFERENCE": "Live", "EVENT_ID_CANON": "l1", "CONFERENCE URL": "https://l1.example/", "START DATE": "2027-01-01", "REFRESH_SKIP": ""}]}
    q = cc.build_queue(inputs, {})
    assert set(q["Cybersecurity"]["ids"]) == {"d1", "l1"} and not q["Cybersecurity"]["dup_ids"]


# ---- the shadow readers read the approved file (complete) and only Open/Upcoming rows, which the policy never skips
def test_shadow_readers_never_see_a_skipped_row_as_live():
    from scripts import shadow_finder as SF
    from scripts import shadow_reader as SR
    rows = [{"CONFERENCE": "Closed and skipped", "EVENT_ID": "a", "STATUS": "Closed", "EDITION": "2027", "START DATE": "2027-03-01", "CONFERENCE URL": "https://a.example/", "_market": "Cybersecurity"},
            {"CONFERENCE": "Upcoming", "EVENT_ID": "b", "STATUS": "Upcoming", "EDITION": "2027", "START DATE": "2027-04-01", "CONFERENCE URL": "https://b.example/", "_market": "Cybersecurity"},
            {"CONFERENCE": "Open", "EVENT_ID": "c", "STATUS": "Open", "EDITION": "2027", "START DATE": "2027-05-01", "CONFERENCE URL": "https://c.example/", "_market": "Cybersecurity"}]
    assert {r["CONFERENCE"] for r in SR.select_rows(rows, "2026-10-17", 100)} == {"Upcoming", "Open"}
    assert {e["event"] for e in SF.select_events(rows, "2026-10-17", 100)} == {"Upcoming", "Open"}


# ---- sponsor prefill and the sponsor-only pass: a skipped row is not in the new audited file, so there is nothing to ask and nothing to carry into it
def test_sponsor_prefill_with_a_skipped_row_absent_from_the_new_file_writes_nothing_for_it(tmp_path):
    from test_sponsor_prefill import Env, not_due_id, read_rows, row
    a, b = not_due_id("ev"), not_due_id("other")
    env = Env(tmp_path, [row(a)], [row(a, "Yes", "https://s.example/a", "1 USD", quote="q"), row(b, "Yes", "https://s.example/b", "2 USD", quote="q")],
              links={"https://s.example/a": "alive", "https://s.example/b": "alive"})
    line = env.run(apply=True)
    assert "1 carried" in line
    rows = read_rows(env.audited)
    assert len(rows) == 1 and rows[0]["EVENT_ID"] == "UP-" + a                                               # the skipped row b was not added
    assert set(env.report()) == {a}                                                                          # and is not in the report either


# ---- scripts/check_commitments.py and weekly_deliverable.py read the APPROVED file, which holds a carried row exactly as it was accepted
def test_a_carried_row_is_the_approved_row_unchanged():
    """weekend_import appends the prior accepted row object itself (rows.append(pr)); the candidate file is written from those dicts, so a carried row is identical to the approved one."""
    src = (ROOT / "scripts" / "weekend_import.py").read_text(encoding="utf-8")
    assert "rows.append(pr)" in src and 'sources.append("prior")' in src
