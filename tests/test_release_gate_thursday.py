"""ACT-70 on the release gate: the Thursday pre-flight (patches, awards waiting for ids, switches, customer sheets and coverage, verdict, operator-only email, exit 0) and the conference Provisional
rows in the gate's counts and coverage; plus the contradictory snapshot line. A small world in a temp folder; no live file, no network, no email (the mailer is a stub)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts import release_gate as rg                                      # noqa: E402
from test_release_gate import world, opts, NOW, drow, write, COLS, ON      # noqa: E402

THU = date(2026, 10, 15)
THU_NOW = datetime(2026, 10, 15, 18, 0)
ENV_ALL = {"CFP_AWARDS_NEW_EVENTS": "1", "CFP_AWARDS_AUTOADD_APPLY": "1", "CFP_AUTOADD_APPLY": "1", "CFP_REFRESH_APPLY": "1", "CFP_RECAP_TO": "me@example.org",
           "CFP_SMTP_HOST": "smtp.example.org", "CFP_SMTP_PORT": "587", "CFP_SMTP_USER": "user@example.org", "CFP_SMTP_PASS": "s3cret-pass-DO-NOT-PRINT"}

BS = chr(92)
NL = chr(10)
STEP_LINE = '[void]$steps.Add(@("$cfpDir' + BS + 'shadow_reader.py", "--markets") + $conf + @("--max-minutes", "45", "--run-log", $RunLog))'
RUN_MONTHLY = NL.join(["# ---- STEP 0: INTAKE ----", "# ---- STEP 0a0: CUSTOMER COVERAGE ----", "# ---- STEP 0a1: ADD MISSING CUSTOMER ROWS ----", "# ---- STEP 0a1b: CUSTOMER AWARDS ----",
                       "# ---- STEP 0a: PERMANENT IDS ----", "# ---- STEP 0a2: AWARDS REFRESH PLAN ----", "# ---- STEP 0b: CANARY ----", "    " + STEP_LINE, ""])
HEAD = NL.join(["--- a/Markets/run_monthly.ps1", "+++ b/Markets/run_monthly.ps1", "@@ -1 +1,3 @@", ""])
PATCH_MARKER = HEAD + NL.join(["+# ---- STEP 0a3: CONFERENCE REFRESH PLAN (ACT-33) ----", "+if ($x) { 1 }", ""])
PATCH_LINE = HEAD + NL.join(["+    # a comment that is not code", "+        " + STEP_LINE, ""])
PATCH_OTHER = "--- a/Markets/run_overnight.ps1\n+++ b/Markets/run_overnight.ps1\n@@ -1 +1,3 @@\n+            try { & py sponsor_prefill.py --apply } catch { 1 }\n"


def thursday_world(tmp_path: Path, patches=(("ACT-20-run_monthly.ps1.patch", PATCH_LINE),), live=RUN_MONTHLY, **kw):
    w = world(tmp_path, **kw)
    (w.md / "run_monthly.ps1").write_text(live, encoding="utf-8")
    pd = w.patches = tmp_path / "patches"
    pd.mkdir()
    for name, text in patches:
        (pd / name).write_text(text, encoding="utf-8")
    return w


def thursday(w, env=None, now=THU_NOW, snapshot_age_days=None):
    o = rg.Opts(THU, now, True, w.md, w.db, w.snaps, None, w.weekly, None, w.qa, w.commit, w.given, w.ledger)
    return rg.evaluate_thursday(o, ENV_ALL if env is None else env, w.patches)


def chk(rep, cid):
    return next(c for c in rep["checks"] if c["id"] == cid)


def set_snapshot_age(w, days):
    stamp = (THU_NOW - timedelta(days=days)).strftime("%Y%m%d-%H%M%S")
    for client in ("arnica", "utility", "arnica-awards", "utility-awards"):
        folder = w.snaps / client
        for f in list(folder.glob("*.csv")):
            f.rename(folder / f"{client}_{stamp}.csv")


# ------------------------------------------------------------------ (t1) patches
def test_a_patch_is_applied_when_its_step_marker_or_its_own_added_line_is_in_the_live_script(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-20-run_monthly.ps1.patch", PATCH_LINE), ("ACT-33-run_monthly.ps1.patch", PATCH_MARKER)))
    ps = rg.patches_status(w.md, w.patches)
    by = {p["name"]: p for p in ps["patches"]}
    assert by["ACT-20-run_monthly.ps1.patch"]["applied"] is True, "the added step line is in the live script"
    assert by["ACT-33-run_monthly.ps1.patch"]["applied"] is False and by["ACT-33-run_monthly.ps1.patch"]["how"] == "STEP 0a3"
    assert ps["markers"]["0a1b"] is True and ps["markers"]["0a3"] is False and ps["markers"]["0b"] is True


def test_the_repo_patch_missing_from_the_live_script_is_named_not_applied_and_the_verdict_has_notes(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-33-run_monthly.ps1.patch", PATCH_MARKER),))
    rep = thursday(w)
    c = chk(rep, "t1")
    assert c["status"] == "WARN" and any("ACT-33" in r and "NOT in the live script" in r for r in c["rows"])
    assert rep["verdict"] == "READY WITH NOTES"


def test_a_patch_held_on_purpose_is_information_not_a_warning_until_its_date_has_passed(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-33-run_monthly.ps1.patch", PATCH_MARKER),))
    (w.patches / "HELD.json").write_text(json.dumps({"ACT-33-run_monthly.ps1.patch": {"until": "2026-10-18", "why": "after Saturday's run"}}), encoding="utf-8")
    rep = thursday(w)
    c = chk(rep, "t1")
    assert c["status"] == "PASS" and rep["verdict"] == "READY"
    assert any(r.startswith("INFO ACT-33") and "ON PURPOSE until 2026-10-18" in r and "after Saturday's run" in r for r in c["rows"])
    assert not any(r.startswith("WARN") for r in c["rows"]) and "1 held on purpose" in c["summary"]
    assert rep["facts"]["patches_held"] == ["ACT-33-run_monthly.ps1.patch"]
    o = rg.Opts(date(2026, 10, 19), datetime(2026, 10, 19, 18, 0), True, w.md, w.db, w.snaps, None, w.weekly, None, w.qa, w.commit, w.given, w.ledger)
    late = next(c for c in rg.thursday_checks(o, ENV_ALL, w.patches)[0] if c["id"] == "t1")
    assert late["status"] == "WARN" and any(r.startswith("WARN ACT-33") for r in late["rows"]), "a hold never outlives its date"


def test_a_hold_does_not_hide_a_patch_that_is_not_named_or_whose_hold_file_is_broken(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-33-run_monthly.ps1.patch", PATCH_MARKER), ("ACT-35-run_monthly.ps1.patch", PATCH_MARKER.replace("0a3", "0a4"))))
    (w.patches / "HELD.json").write_text(json.dumps({"ACT-33-run_monthly.ps1.patch": {"until": "2026-10-18", "why": "x"}}), encoding="utf-8")
    c = chk(thursday(w), "t1")
    assert c["status"] == "WARN" and any(r.startswith("WARN ACT-35") for r in c["rows"]) and any(r.startswith("INFO ACT-33") for r in c["rows"])
    (w.patches / "HELD.json").write_text("{not json", encoding="utf-8")
    assert chk(thursday(w), "t1")["status"] == "WARN" and rg.held_patches(w.patches) == {}


def test_a_patch_for_another_script_is_judged_against_that_script(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-64-run_overnight.ps1.patch", PATCH_OTHER),))
    c = chk(thursday(w), "t1")
    assert c["status"] == "WARN" and "could not be read" in " ".join(c["rows"]), "run_overnight.ps1 is not there: said so, not silently passed"
    (w.md / "run_overnight.ps1").write_text("try { & py sponsor_prefill.py --apply } catch { 1 }", encoding="utf-8")
    assert chk(thursday(w), "t1")["status"] == "PASS"


def test_an_unreadable_live_script_is_a_fail_to_fix_before_02_00(tmp_path):
    w = thursday_world(tmp_path)
    (w.md / "run_monthly.ps1").unlink()
    rep = thursday(w)
    assert chk(rep, "t1")["status"] == "FAIL" and rep["verdict"] == "FIX BEFORE 02:00"


# ------------------------------------------------------------------ (t2) awards waiting
def test_awards_without_a_permanent_id_are_named_with_the_draft_request(tmp_path):
    waiting = {"CONFERENCE": "Brand New Award", "EVENT_ID_CANON": "", "CONFERENCE URL": "https://n.example/", "SUBMISSION URL": "https://n.example/a/b", "START DATE": "", "Market": "Utility", "DUP_OF": ""}
    w = thursday_world(tmp_path, awards_input_extra=[waiting])
    (w.qa / "2026-10-12").mkdir(parents=True)
    (w.qa / "2026-10-12" / "request_to_upstream_awards_2026-10-12.md").write_text("draft", encoding="utf-8")
    c = chk(thursday(w), "t2")
    assert c["status"] == "WARN" and any("Brand New Award" in r for r in c["rows"]) and any("request_to_upstream_awards_2026-10-12.md" in r for r in c["rows"])
    assert chk(thursday(thursday_world(tmp_path / "b")), "t2")["status"] == "PASS"


# ------------------------------------------------------------------ (t3) switches and mail
def test_each_switch_is_ON_OFF_or_not_set_with_what_it_means_and_no_value_is_printed(tmp_path):
    w = thursday_world(tmp_path)
    rep = thursday(w, env={"CFP_AWARDS_NEW_EVENTS": "1", "CFP_AUTOADD_APPLY": "0", **{k: v for k, v in ENV_ALL.items() if k.startswith(("CFP_RECAP", "CFP_SMTP"))}})
    sw = rep["facts"]["switches"]
    assert sw == {"CFP_AWARDS_NEW_EVENTS": "ON", "CFP_AWARDS_AUTOADD_APPLY": "not set", "CFP_AUTOADD_APPLY": "OFF", "CFP_REFRESH_APPLY": "not set"}
    text = "\n".join(chk(rep, "t3")["rows"])
    assert "CFP_AWARDS_NEW_EVENTS is ON - Friday: a NEW award" in text and "CFP_AUTOADD_APPLY is OFF - Saturday: Saturday only REPORTS" in text
    blob = json.dumps(rep["facts"]) + rg.thursday_markdown(rep) + "".join(rg.thursday_email(rep)) + json.dumps([dict(c) for c in rep["checks"]])
    for secret in ("s3cret-pass-DO-NOT-PRINT", "me@example.org", "smtp.example.org", "user@example.org"):
        assert secret not in blob, "values are never printed"
    assert "CFP_SMTP_PASS set" in text


def test_missing_mail_settings_are_a_warning_naming_the_variable_only(tmp_path):
    w = thursday_world(tmp_path)
    env = {k: v for k, v in ENV_ALL.items() if k != "CFP_SMTP_PASS"}
    c = chk(thursday(w, env=env), "t3")
    assert c["status"] == "WARN" and "CFP_SMTP_PASS" in c["rows"][0] and "s3cret" not in "".join(c["rows"])


def test_env_value_reads_the_given_environment_not_the_machine():
    assert rg.env_value("CFP_X", {"CFP_X": "1"}) == "1" and rg.env_value("CFP_X", {}) == ""


# ------------------------------------------------------------------ (t4) sheets and coverage
def test_snapshot_ages_are_information_until_the_intake_has_missed_a_week(tmp_path):
    w = thursday_world(tmp_path)
    set_snapshot_age(w, 5.7)
    c = chk(thursday(w), "t4")
    assert c["status"] == "PASS" and any("5.7 days old" in r and "Saturday" in r for r in c["rows"])
    set_snapshot_age(w, 8.0)
    assert chk(thursday(w), "t4")["status"] == "WARN"
    set_snapshot_age(w, 11.0)
    assert chk(thursday(w), "t4")["status"] == "FAIL"


def add_customer_conference_not_in_queue(w):
    con = sqlite3.connect(w.db)
    con.execute("insert into client_conferences values (?,?,?,?,?,?,?,?,?)", ("arnica", "Missing Conf 2027", "2027-missing", "https://missing.example.org/", "", "", "2027-05-01", 0, ""))
    con.commit()
    con.close()


def test_a_customer_conference_not_in_the_research_queue_is_a_fix_unless_the_add_switch_is_on(tmp_path):
    w = thursday_world(tmp_path)
    add_customer_conference_not_in_queue(w)
    env_off = {**ENV_ALL, "CFP_AUTOADD_APPLY": ""}
    rep = thursday(w, env=env_off)
    c = chk(rep, "t4")
    assert c["status"] == "FAIL" and any("Missing Conf 2027" in r and "will NOT research them" in r for r in c["rows"]) and rep["verdict"] == "FIX BEFORE 02:00"
    assert rep["facts"]["conference_coverage"]["not_in_queue"] == 1
    rep_on = thursday(w, env=ENV_ALL)
    c_on = chk(rep_on, "t4")
    assert c_on["status"] == "PASS" and any("Saturday adds them" in r for r in c_on["rows"]) and rep_on["verdict"] in ("READY", "READY WITH NOTES")


def test_a_customer_award_not_in_the_research_queue_is_a_fix_unless_the_awards_add_switch_is_on(tmp_path):
    w = thursday_world(tmp_path)
    p = next((w.snaps / "utility-awards").glob("*.csv"))
    p.write_text(p.read_text(encoding="utf-8") + "Totally New Award,,,,,,https://new.example/awards/n\n", encoding="utf-8")
    rep = thursday(w, env={**ENV_ALL, "CFP_AWARDS_AUTOADD_APPLY": ""})
    assert chk(rep, "t4")["status"] == "FAIL" and rep["facts"]["awards_not_in_queue"] == 1
    assert chk(thursday(w, env=ENV_ALL), "t4")["status"] == "PASS"


def test_the_dry_run_adds_nothing_to_the_markets_folder(tmp_path):
    w = thursday_world(tmp_path)
    before = {p: p.read_bytes() for p in w.md.rglob("*") if p.is_file()}
    thursday(w)
    after = {p: p.read_bytes() for p in w.md.rglob("*") if p.is_file()}
    assert before == after


# ------------------------------------------------------------------ verdict, email, exit code
def test_a_healthy_thursday_is_READY(tmp_path):
    w = thursday_world(tmp_path, patches=())
    rep = thursday(w)
    assert rep["verdict"] == "READY", [(c["id"], c["status"], c["summary"]) for c in rep["checks"] if c["status"] != "PASS"]


def test_the_email_goes_to_the_operator_only_through_the_same_mailer_with_no_attachment(tmp_path):
    w = thursday_world(tmp_path, patches=(("ACT-33-run_monthly.ps1.patch", PATCH_MARKER),))
    rep = thursday(w)
    sent = []
    assert rg.send(rep, mailer=lambda subj, body, **kw: sent.append((subj, body, kw)) or True) is True
    subj, body, kw = sent[0]
    assert subj == "CFP Thursday pre-flight: READY WITH NOTES" and kw["to_env"] == "CFP_RECAP_TO" and not kw.get("attachments")
    assert "ACT-33" in body and "Friday 02:00" in body and "operator only" in body


def test_main_thursday_dry_run_writes_only_under_the_qa_root_and_always_exits_0(tmp_path, capsys, monkeypatch):
    w = thursday_world(tmp_path)
    monkeypatch.setattr(rg, "env_value", lambda name, env=None: ENV_ALL.get(name, ""))
    monkeypatch.setattr(rg, "PATCHES", w.patches)
    monkeypatch.setattr(rg.evaluate_thursday, "__defaults__", (None, w.patches))
    before = {p for p in tmp_path.rglob("*") if p.is_file() and w.qa not in p.parents}
    rc = rg.main(["--thursday", "--dry-run", "--on", "2026-10-15", "--now", "2026-10-15T18:00:00", "--markets-dir", str(w.md), "--db", str(w.db), "--snapshots-dir", str(w.snaps),
                  "--weekly-dir", str(w.weekly), "--qa-root", str(w.qa)])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("GATE: READY") and "not sent" in out
    after = {p for p in tmp_path.rglob("*") if p.is_file() and w.qa not in p.parents}
    assert after == before, "nothing is written outside the QA root"
    assert any(w.qa.rglob("thursday.md")) and any(w.qa.rglob("thursday_email.txt"))
    # a fault anywhere still exits 0 with a verdict line
    rc2 = rg.main(["--thursday", "--dry-run", "--on", "not-a-date"])
    assert rc2 == 0 and "GATE: UNKNOWN" in capsys.readouterr().out


# ------------------------------------------------------------------ B: conference provisional rows in the gate
def conference_provisional_world(tmp_path):
    w = world(tmp_path)
    held = drow("Held Conf 2027", "2027-held", "Cybersecurity", **{"STATUS DETAILS": "The event is confirmed for March 3-4, 2027, and registration is open."})
    cyber_in = [r for r in __import__("csv").DictReader(open(w.md / "Cybersecurity_input.csv", encoding="utf-8"))]
    cyber_in.append({"CONFERENCE": "Held Conf 2027", "EVENT_ID_CANON": "2027-held", "CONFERENCE URL": held["CONFERENCE URL"], "SUBMISSION URL": "", "START DATE": "2027-03-03", "Market": "Cybersecurity", "DUP_OF": ""})
    write(w.md / "Cybersecurity_input.csv", cyber_in, ["CONFERENCE", "EVENT_ID_CANON", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "Market", "DUP_OF"])
    raw = [*w.cyber, held]
    write(w.md / "Cybersecurity_audited.csv", raw)
    ts = datetime(2026, 10, 10, 15, 34).timestamp()
    os.utime(w.md / "Cybersecurity_audited.csv", (ts, ts))
    write(w.md / "Cybersecurity_audited.identity.csv", [{"OUTPUT_EVENT_ID": r["EVENT_ID"], "OUTPUT_CONFERENCE": r["CONFERENCE"], "INPUT_CONFERENCE": r["CONFERENCE"], "EVENT_ID_CANON": r["EVENT_ID"]} for r in raw],
          ["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"])
    (w.db.parent / "market_sheets").mkdir(exist_ok=True)
    (w.db.parent / "market_sheets" / "cyber_seed.csv").write_text("EVENT_ID,EVENT_ID_CANON\n2027-alpha,2027-alpha\n2027-beta,2027-beta\n", encoding="utf-8")
    wk = w.md / "weekend" / "20261010-230054"
    wk.mkdir(parents=True)
    (wk / "weekend_import.log").write_text("ACCEPTANCE GATE - Cybersecurity_audited.candidate.csv  (3 rows)\n  [FAIL] 4    No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)  (1)\n"
                                           "           - Held Conf 2027: The event is confirmed for March 3-4, 2027, and registrat\n  RESULT: REJECTED\n", encoding="utf-8")
    con = sqlite3.connect(w.db)
    con.execute("insert into client_conferences values (?,?,?,?,?,?,?,?,?)", ("arnica", "Held Conf 2027", "2027-held", held["CONFERENCE URL"], "", "", "2027-03-03", 0, ""))
    con.commit()
    con.close()
    return w


def test_a_held_conference_is_counted_as_provisional_and_its_customer_row_is_on_the_page_for_that_reason(tmp_path):
    w = conference_provisional_world(tmp_path)
    rep = rg.evaluate(rg.Opts(ON, NOW, True, w.md, w.db, w.snaps, None, w.weekly, None, w.qa, w.commit, w.given, w.ledger))
    assert rep["counts"]["provisional_conference"] == 1 and rep["counts"]["conference"] == 5
    e = next(c for c in rep["checks"] if c["id"] == "e")
    assert e["status"] == "WARN" and any("Held Conf 2027" in r and "left blank: STATUS DETAILS" in r for r in e["rows"])
    arnica = rep["coverage"]["conference"]["arnica"]
    held = [m for m in arnica["missing"] if m["name"] == "Held Conf 2027"]
    assert held and held[0]["reason"] == rg.R_PROV and held[0]["on_page"] is True and arnica["provisional"] == 1
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert not any("Held Conf 2027" in r and r.startswith("WARN") for r in b["rows"]), "a Provisional row is on the page: not a gap"
    c = next(c for c in rep["checks"] if c["id"] == "c")
    assert any("Held Conf 2027" in r and "as Provisional" in r and r.startswith("INFO") for r in c["rows"])
    assert any("Provisional" in x for x in rg.plain_lines(rep))


def test_the_snapshot_line_is_no_longer_self_contradictory(tmp_path):
    w = world(tmp_path, snapshot_age_days=3.0)
    c = next(c for c in rg.evaluate(opts(w)) ["checks"] if c["id"] == "f")
    assert c["status"] == "WARN" and "are fresh" not in c["title"] and "fresh" not in c["summary"]
    assert "older than 2 days" in c["summary"] and "of the four" in c["summary"]
    ok = next(c for c in rg.evaluate(opts(world(tmp_path / "ok", snapshot_age_days=0.5)))["checks"] if c["id"] == "f")
    assert ok["status"] == "PASS" and ok["summary"] == "all four snapshots are under 2 days old"


def test_main_runs_with_stdout_redirected_to_a_stringio():
    """weekend_recap.py captures the gate's output in a StringIO; main() must not need a real console.
    Unguarded, the Sunday pre-flight verdict read UNKNOWN (AttributeError: reconfigure) 2026-10-12 to 2026-10-18."""
    import contextlib
    import io

    import pytest

    import scripts.release_gate as rg
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(SystemExit) as e:
            rg.main(["--help"])
    assert e.value.code == 0
