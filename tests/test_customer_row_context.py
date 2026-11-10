"""ACT-72, the customer-context plan steps 2, 3, 6 and 8 (D9 and D10 on Daily Review, Matt 2026-11-09): the customer's own sheet row reaches the
research as CONTEXT, never evidence. Every row, name, address and id here is MADE UP: this repository is public, and the real cells (which keep
the customer's contacts, D9) exist only at run time, in the input lists outside the repo."""
from __future__ import annotations

import csv
import importlib.util
import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import pytest

from scripts import customer_row_context as c
from src.cfp_monitor.unified_patch import PatchDoesNotApply, apply_unified

ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "docs" / "control" / "patches"
RMA_PATCH = PATCHES / "ACT-72-run_market_audit.py.patch"
RM_PATCH = PATCHES / "ACT-72-run_monthly.ps1.patch"
LIVE_RMA = c.MARKETS / "run_market_audit.py"
LIVE_RM = c.MARKETS / "run_monthly.ps1"
T = date(2026, 11, 14)


# ------------------------------------------------------------------ the cell
def test_the_cell_carries_the_event_facts_and_their_details_and_notes_with_contacts_kept():
    cell = c.context_cell("Arnica", {"name": "Fake Summit 2027", "link": "https://fake-summit.example/", "place": "Springfield",
                                     "dates": "2027-03-04", "deadline": "2026-12-01", "submission_link": "https://fake-summit.example/cfp",
                                     "status_details": "Call opens in December.", "notes": "Submit by email to talks@fake-summit.example"})
    assert cell.startswith("CUSTOMER ROW (context, not evidence) - Arnica sheet: ")
    for bit in ('name "Fake Summit 2027"', "link https://fake-summit.example/", "place Springfield", "dates 2027-03-04", "their deadline 2026-12-01",
                "their submission link https://fake-summit.example/cfp", "their status details: Call opens in December.",
                "their notes: Submit by email to talks@fake-summit.example"):
        assert bit in cell, bit
    assert "talks@fake-summit.example" in cell, "D9: a contact address is KEPT"


def test_blanks_are_left_out_long_text_is_cut_and_an_empty_row_gives_no_cell():
    cell = c.context_cell("Utility Global", {"name": "Fake Award", "place": "nan", "notes": "x" * 700})
    assert "place" not in cell and "nan" not in cell
    assert cell.endswith("x" * 600 + " (cut).")
    assert c.context_cell("Arnica", {"name": "", "notes": "  "}) == ""


def test_their_status_and_coordinator_contact_are_in_the_cell_and_priority_is_not():
    """D9 clarified (Matt in chat, relayed 2026-11-09): "Yes, include both" - STATUS and COORDINATOR CONTACT. PRIORITY was not asked for."""
    f = c.conference_fields({"their_name": "Fake Con", "status": "Info Needed", "priority": "High", "coordinator_contact": "someone@fake.example"})
    cell = c.context_cell("Arnica", f)
    assert "their status Info Needed" in cell and "their coordinator contact: someone@fake.example" in cell and "High" not in cell
    aw = c.context_cell("Utility Global", c.award_fields({"AWARD": "Fake Award", "SUBMISSION STATUS": "Submitted", "COORDINATOR CONTACT": "Pat, +1 555 0100"}))
    assert "their status Submitted" in aw and "their coordinator contact: Pat, +1 555 0100" in aw


def test_credential_wording_without_punctuation_is_dropped_but_process_text_is_kept():
    """Codex review 2026-11-09, findings 2 and 6. Made-up text only."""
    cells = {0: "their notes: portal password is in the welcome email", 1: "their notes: username is fakeuser", 2: "their notes: login: fakeuser",
             3: "their notes: login required to submit; email the chair", 4: "their notes: Pwd example", 5: "their notes: the user name of the chair is on the page"}
    keep = c.screen(cells, "Awards", [])
    assert sorted(keep) == [3, 5], keep


def test_a_deep_link_beats_a_shared_name():
    """Codex finding 1: two different awards share a name key; the input row's deep link names one of them, and only that one is joined."""
    sheets = {"arnica-awards": [{"AWARD": "Fake Excellence Award", "SUBMISSION URL": "https://one.example/enter", "NOTES": "first"},
                                {"AWARD": "Fake Excellence Award", "SUBMISSION URL": "https://two.example/enter", "NOTES": "second"}]}
    cells = c.award_cells(sheets, [{"CONFERENCE": "Fake Excellence Award", "SUBMISSION URL": "https://two.example/enter", "CONFERENCE URL": "", "DUP_OF": ""}])
    assert "their notes: second" in cells[0] and "first" not in cells[0]


def test_a_requested_market_with_no_input_list_is_failed(tmp_path, capsys):
    """Codex finding 4."""
    md = _markets(tmp_path, 0.2)
    code = c.main(["--markets", "Awards,Utility", "--markets-dir", str(md), "--evidence-dir", str(tmp_path / "ev"), "--today", date.today().isoformat()])
    out = capsys.readouterr().out
    assert code == 1 and "CUSTOMER CONTEXT: FAILED" in out and "Utility: no input list Utility_input.csv" in out


def test_a_login_or_password_pattern_drops_the_cell_and_the_refusal_never_quotes_it():
    refused: list = []
    keep = c.screen({0: "CUSTOMER ROW ... their notes: portal pw: (made up)", 1: "CUSTOMER ROW ... their notes: email the chair"}, "Awards", refused)
    assert list(keep) == [1]
    assert refused == [{"market": "Awards", "row": 2, "why": "a login or password pattern: cell dropped"}]


# ------------------------------------------------------------------ pairing
def test_awards_pair_by_name_or_deep_link_never_an_id_and_duplicates_are_skipped():
    sheets = {"arnica-awards": [{"AWARD": "Fake Prize (2026)", "SUBMISSION URL": "", "NOTES": "a"},
                                {"AWARD": "Other", "SUBMISSION URL": "https://fake-prize.example/enter", "NOTES": "b"}],
              "utility-awards": [{"AWARD": "fake prize 2026", "SUBMISSION URL": "", "NOTES": "c"}]}
    inputs = [{"CONFERENCE": "Fake Prize", "SUBMISSION URL": "", "CONFERENCE URL": "", "DUP_OF": ""},
              {"CONFERENCE": "Renamed", "SUBMISSION URL": "https://fake-prize.example/enter/", "CONFERENCE URL": "", "DUP_OF": ""},
              {"CONFERENCE": "Fake Prize", "SUBMISSION URL": "", "CONFERENCE URL": "", "DUP_OF": "row 1"},
              {"CONFERENCE": "Nobody's", "SUBMISSION URL": "", "CONFERENCE URL": "https://elsewhere.example/", "DUP_OF": ""}]
    cells = c.award_cells(sheets, inputs)
    assert set(cells) == {0, 1}
    assert "Arnica sheet" in cells[0] and "Utility Global sheet" in cells[0] and " || " in cells[0], "both customers' rows, joined"
    assert "their notes: b" in cells[1]


def test_conferences_pair_by_the_coverage_rule_on_our_own_id():
    client = [{"client_key": "arnica", "their_name": "Fake Con", "event_id": "2027-fake-con-springfield", "their_url": "", "event_start_date": "",
               "notes": "ask the chair", "withdrawn_by_customer": 0},
              {"client_key": "arnica", "their_name": "Gone", "event_id": "2027-gone", "withdrawn_by_customer": 1}]
    inputs = {"Cybersecurity": [{"CONFERENCE": "Fake Con", "EVENT_ID_CANON": "2027-fake-con-springfield", "DUP_OF": ""},
                                {"CONFERENCE": "Gone", "EVENT_ID_CANON": "2027-gone", "DUP_OF": ""}]}
    cells = c.conference_cells(client, inputs, {})
    assert list(cells) == [("Cybersecurity", 0)] and "their notes: ask the chair" in cells[("Cybersecurity", 0)]


# ------------------------------------------------------------------ the writer
def _write(p: Path, cols: list[str], rows: list[dict]) -> None:
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)


def test_the_writer_adds_the_column_at_the_end_leaves_every_other_cell_and_keeps_a_backup(tmp_path):
    p = tmp_path / "Awards_input.csv"
    cols = ["CONFERENCE", "NOTES", "REFRESH_SKIP"]
    rows = [{"CONFERENCE": "A, with comma", "NOTES": 'seed "quoted"', "REFRESH_SKIP": ""}, {"CONFERENCE": "B", "NOTES": "", "REFRESH_SKIP": "G2 dormant"}]
    _write(p, cols, rows)
    msg = c.write_column(p, {0: "CUSTOMER ROW (context, not evidence) - Arnica sheet: name \"A\"."})
    assert "read-back proof OK" in msg and (tmp_path / "Awards_input.pre-context.csv").exists()
    got_cols, got = c.read_csv(p)
    assert got_cols == [*cols, "CUSTOMER_ROW"]
    assert [{k: r[k] for k in cols} for r in got] == rows, "good input survives untouched"
    assert got[0]["CUSTOMER_ROW"].startswith("CUSTOMER ROW") and got[1]["CUSTOMER_ROW"] == ""
    c.write_column(p, {})                                                                  # next week the row no longer pairs
    assert [r["CUSTOMER_ROW"] for r in c.read_csv(p)[1]] == ["", ""], "an old cell never survives"


def test_a_failed_read_back_puts_the_file_back(tmp_path, monkeypatch):
    p = tmp_path / "Utility_input.csv"
    _write(p, ["CONFERENCE"], [{"CONFERENCE": "X"}])
    before = p.read_bytes()
    monkeypatch.setattr(c, "read_back", lambda *a, **k: "row 2: column CONFERENCE changed")
    with pytest.raises(RuntimeError, match="was put back"):
        c.write_column(p, {0: "cell"})
    assert p.read_bytes() == before


def _markets(tmp_path: Path, age_days: float) -> Path:
    md = tmp_path / "Markets"
    md.mkdir()
    _write(md / "Awards_input.csv", ["CONFERENCE", "SUBMISSION URL", "CONFERENCE URL", "DUP_OF", "REFRESH_SKIP"],
           [{"CONFERENCE": "Fake Prize", "SUBMISSION URL": "", "CONFERENCE URL": "", "DUP_OF": "", "REFRESH_SKIP": ""}])
    for client in c.AWARD_CLIENTS:
        d = md / "customer_snapshots" / client
        d.mkdir(parents=True)
        f = d / f"{client}_20261113-020000.csv"
        _write(f, ["AWARD", "SUBMISSION URL", "NOTES"], [{"AWARD": "Fake Prize", "SUBMISSION URL": "", "NOTES": "fake note"}])
        old = time.time() - age_days * 86400
        os.utime(f, (old, old))
    return md


def test_friday_writes_awards_context_and_says_healthy(tmp_path, capsys):
    md = _markets(tmp_path, 0.2)
    code = c.main(["--markets", "Awards", "--markets-dir", str(md), "--apply", "--evidence-dir", str(tmp_path / "ev"), "--today", date.today().isoformat()])
    out = capsys.readouterr().out
    assert code == 0 and "CUSTOMER CONTEXT: HEALTHY - 1 of 1 research rows carry the customer's row" in out
    assert "fake note" not in out, "a cell is never printed"
    assert "fake note" in c.read_csv(md / "Awards_input.csv")[1][0]["CUSTOMER_ROW"]
    assert (tmp_path / "ev" / "customer_context.csv").exists() and (tmp_path / "ev" / "customer_context_refused.csv").exists()


def test_an_old_sheet_copy_is_degraded_and_says_which(tmp_path, capsys):
    md = _markets(tmp_path, 5)
    code = c.main(["--markets", "Awards", "--markets-dir", str(md), "--evidence-dir", str(tmp_path / "ev"), "--today", date.today().isoformat()])
    out = capsys.readouterr().out
    assert code == 2 and "CUSTOMER CONTEXT: DEGRADED" in out and "Arnica awards sheet copy is 5 days old" in out
    assert "CUSTOMER_ROW" not in c.read_csv(md / "Awards_input.csv")[0], "report only without --apply"


def test_the_switch_off_empties_the_column(tmp_path, capsys):
    md = _markets(tmp_path, 0.2)
    c.main(["--markets", "Awards", "--markets-dir", str(md), "--apply", "--evidence-dir", str(tmp_path / "ev"), "--today", date.today().isoformat()])
    assert c.main(["--markets", "Awards", "--markets-dir", str(md), "--clear"]) == 0
    assert "CUSTOMER CONTEXT: OFF" in capsys.readouterr().out
    assert [r["CUSTOMER_ROW"] for r in c.read_csv(md / "Awards_input.csv")[1]] == [""]


# ------------------------------------------------------------------ the patches (applied to COPIES of the live Markets scripts)
def _added(p: Path) -> list[str]:
    return [ln[1:] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def _removed(p: Path) -> list[str]:
    return [ln[1:] for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("-") and not ln.startswith("---")]


def test_the_run_patch_only_adds_and_the_prompt_patch_changes_one_line_only_by_appending_the_block():
    assert _removed(RM_PATCH) == []
    gone = _removed(RMA_PATCH)
    assert gone == ["    - Prior Opportunity Type: {opp_type}"], gone
    assert "    - Prior Opportunity Type: {opp_type}{customer_block}" in _added(RMA_PATCH), "the line is kept and only gains the block"


def test_a_patch_whose_context_moved_is_refused_not_applied_fuzzily():
    with pytest.raises(PatchDoesNotApply):
        apply_unified("nothing like the script\n", RMA_PATCH.read_text(encoding="utf-8"))


def _load(text: str, tmp_path: Path, name: str):
    c._stub_genai()
    f = tmp_path / f"{name}.py"
    f.write_text(text, encoding="utf-8")
    if (c.MARKETS / "standing_rules.md").exists():
        (tmp_path / "standing_rules.md").write_bytes((c.MARKETS / "standing_rules.md").read_bytes())
    spec = importlib.util.spec_from_file_location(name, f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not LIVE_RMA.exists(), reason="the live Markets script is not on this machine")
def test_the_prompt_patch_applies_to_the_live_script_and_a_row_without_context_gets_the_same_prompt(tmp_path):
    live = LIVE_RMA.read_text(encoding="utf-8").replace("\r\n", "\n")
    patched = live if "customer_block" in live else apply_unified(live, RMA_PATCH.read_text(encoding="utf-8"))
    old = _load(live, tmp_path, "rma_old")
    new = _load(patched, tmp_path, "rma_new")
    row = {"CONFERENCE": "Fake Con 2027", "CONFERENCE URL": "https://fake-con.example/", "LOCATION": "Springfield", "OPPORTUNITY_TYPE": "Speaking"}
    if "customer_block" not in live:
        assert new.build_conference_prompt(dict(row), "2026-11-14") == old.build_conference_prompt(dict(row), "2026-11-14")
    assert new.build_conference_prompt({**row, "CUSTOMER_ROW": ""}, "2026-11-14") == new.build_conference_prompt(dict(row), "2026-11-14")
    cell = 'CUSTOMER ROW (context, not evidence) - Arnica sheet: name "Fake Con" | their notes: submit by email.'
    for build in (new.build_conference_prompt, new.build_awards_prompt, new.build_narrow_prompt):
        p = build({**row, "CUSTOMER_ROW": cell}, "2026-11-14")
        assert "CUSTOMER'S OWN ROW (context, NOT evidence; see rule C):" in p and cell in p
        assert "NEVER copy a value from it into an output field" in p
        assert "Never return NOTES, and never return the" in p and "customer's contact or status as a value." in p
        assert "Your sheet says <X>; the event's page says <Y>." in p


@pytest.mark.skipif(not LIVE_RM.exists(), reason="the live Markets script is not on this machine")
def test_the_run_patch_puts_step_0a4_after_the_refresh_plan_and_before_the_canary_with_an_off_switch():
    live = LIVE_RM.read_text(encoding="utf-8").replace("\r\n", "\n")
    t = live if "STEP 0a4: CUSTOMER CONTEXT" in live else apply_unified(live, RM_PATCH.read_text(encoding="utf-8"))
    a3, a4, b = t.index("STEP 0a3: CONFERENCE REFRESH PLAN"), t.index("STEP 0a4: CUSTOMER CONTEXT"), t.index("STEP 0b: CANARY")
    assert a3 < a4 < b
    added = "\n".join(_added(RM_PATCH))
    assert "customer_row_context.py" in added and "--apply" in added and "$env:CFP_CUSTOMER_CONTEXT -eq '0'" in added and "@('--clear')" in added
    assert "-not $WhatIf" in added and "customer_row_answers.py" in added and "CUSTOMER ROWS:*" in added


def test_the_thursday_preflight_sees_both_act_72_patches(tmp_path):
    from scripts import release_gate as rg
    md = tmp_path / "Markets"
    md.mkdir()
    (md / "run_monthly.ps1").write_text("# STEP 0a3: x\n", encoding="utf-8")
    (md / "run_market_audit.py").write_text("x = 1\n", encoding="utf-8")
    st = {p["name"]: p for p in rg.patches_status(md)["patches"]}
    assert st["ACT-72-run_monthly.ps1.patch"]["applied"] is False and st["ACT-72-run_monthly.ps1.patch"]["how"] == "STEP 0a4"
    assert st["ACT-72-run_market_audit.py.patch"]["applied"] is False, "the prompt patch is read, not 'could not be read'"
    (md / "run_market_audit.py").write_text("x = 1\n" + "\n".join(_added(RMA_PATCH)) + "\n", encoding="utf-8")
    assert {p["name"]: p for p in rg.patches_status(md)["patches"]}["ACT-72-run_market_audit.py.patch"]["applied"] is True


# ------------------------------------------------------------------ the recap (plan step 8)
def test_the_recap_repeats_the_verdict_flags_anything_but_healthy_and_says_when_the_step_did_not_run():
    from scripts import weekend_recap as wr
    ok = wr.customer_context_sentences({"customer_context": "HEALTHY - 245 of 298 research rows carry the customer's row",
                                        "customer_rows": "224 rows; 180 researched"}, "saturday")
    assert ok[0].startswith("Customer context in the research") and ok[1] == "Customer rows answered: 224 rows; 180 researched."
    assert wr.customer_context_sentences({"customer_context": "DEGRADED - x"}, "friday")[0].startswith("FLAG - ")
    assert wr.customer_context_sentences({"customer_rows": "x"}, "friday") == [
        "Customer context in the research: no CUSTOMER CONTEXT line in the log - the step did not run, so this run's research had no customer context."]
    log = "CUSTOMER CONTEXT: HEALTHY - 1 of 1\nCUSTOMER ROWS: 2 rows\n"
    s = wr.parse_saturday(log)
    assert s["customer_context"] == "HEALTHY - 1 of 1" and s["customer_rows"] == "2 rows"
