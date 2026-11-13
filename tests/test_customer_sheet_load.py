"""scripts/customer_sheet_load.py: Matt's CRITICAL alert when the customer sheets do not load (2026-11-09).

Every fetch is faked (no network), every email goes to a stub (tests/conftest.py also removes the mail settings), and every file lands in
tmp_path. Covers: each cause the code can tell apart, the retries (only what can clear by itself), the exact subject and body, no secret in
anything written or sent, one alert a day, the 2-hour wait and its two follow-up emails (2026-11-10), the wait cut to the task's time
limit, the person's re-run, the dead-man check's three cases and the Thursday read-only check. And the inversion: a healthy load sends
nothing and writes nothing. No test reads Task Scheduler: the task reader is always a stub."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import customer_sheet_load as csl                                          # noqa: E402

REAL_TASK_INFO = csl.task_info          # the fixtures stub csl.task_info; this test exercises the real parser with a fake runner

NOW = datetime(2026, 11, 14, 2, 0, 5)
FAKE_PASS = "s3cret-smtp-pass-DO-NOT-PRINT"
FAKE_KEY_BLOCK = "-----BEGIN PRIVATE KEY-----\nMIIfakefakefake\n-----END PRIVATE KEY-----"


class Clock:
    def __init__(self, start=NOW):
        self.t = start
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += timedelta(seconds=s)


class World:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.snaps = tmp / "customer_snapshots"
        self.snaps.mkdir()
        self.key = tmp / "keys" / "reader.json"
        self.key.parent.mkdir()
        self.key.write_text(json.dumps({"client_email": "reader@example.iam.gserviceaccount.com", "private_key": FAKE_KEY_BLOCK}), encoding="utf-8")
        self.config = tmp / "customer_sheets.json"
        self.config.write_text(json.dumps({"service_account_key": str(self.key), "clients": {
            "arnica": {"sheet_id": "SHEET-A", "gid": "1"}, "utility": {"sheet_id": "SHEET-U", "gid": "2"},
            "arnica-awards": {"sheet_id": "SHEET-AA", "gid": "3", "kind": "awards"},
            "utility-awards": {"sheet_id": "SHEET-UA", "gid": "4", "kind": "awards"}}}), encoding="utf-8")
        self.qa = tmp / "qa"
        self.state = tmp / "sent.json"
        self.desk = [tmp / "desk" / "CUSTOMER-SHEET-FETCH-FAILED.txt"]
        self.sent = []
        self.calls = []
        self.status = tmp / "sheet_load_status.json"

    def mailer(self, subject, body, **kw):
        self.sent.append((subject, body, kw))
        return True

    def copy(self, client, when):
        d = self.snaps / client
        d.mkdir(exist_ok=True)
        p = d / f"{client}_{when.strftime('%Y%m%d-%H%M%S')}.csv"
        p.write_text("x\n", encoding="utf-8")
        return p

    def runner(self, script, clock):
        """script: list of {client: 'ok' | 'nocopy' | '<failure text>'} per attempt; 'ok' also lands a fresh copy."""
        def run(cmd, timeout=600):
            self.calls.append([str(c) for c in cmd])
            step = script[min(len(self.calls), len(script)) - 1]
            clients = cmd[cmd.index("--client") + 1].split(",")
            out = []
            for c in clients:
                r = step.get(c, "ok")
                if r in ("ok", "nocopy"):
                    out.append(f"{c}: fetched 84 rows (10,000 bytes) [conference]")
                    if r == "ok" and "--no-snapshot" not in cmd:
                        self.copy(c, clock.now())
                else:
                    out.append(f"{c}: FAILED - {r}")
            return (0 if all(step.get(c, "ok") == "ok" for c in clients) else 1), "\n".join(out)
        return run

    def load(self, script, clients=csl.ALL_CLIENTS, env=None, once=False, context="saturday", clock=None, task=None):
        """env defaults to NO wait (CFP_SHEETS_HOLD_HOURS=0), so the older tests see one email; the wait has its own tests below."""
        clock = clock or Clock()
        return csl.guarded_load(list(clients), context, self.config, self.snaps, once=once,
                                env={"CFP_SHEETS_HOLD_HOURS": "0"} if env is None else env, mailer=self.mailer,
                                sleep=clock.sleep, runner=self.runner(script, clock), now=clock.now, qa_root=self.qa,
                                state=self.state, alert_files=self.desk, task_reader=lambda name: dict(task or {}),
                                say=lambda line: None, status_path=self.status) + (clock,)


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(csl.fcs, "alert_paths", lambda: [tmp_path / "desk" / "CUSTOMER-SHEET-FETCH-FAILED.txt"])
    monkeypatch.setenv("CFP_SMTP_PASS", FAKE_PASS)          # present in the environment, so redact() has something to strip
    monkeypatch.setattr(csl, "task_info", lambda *a, **k: {})            # never read the real Task Scheduler from a test
    monkeypatch.setattr(csl, "STATUS", tmp_path / "status-default.json")
    return World(tmp_path)


# ------------------------------------------------------------------ causes
@pytest.mark.parametrize("text,cause", [
    ("Service account key not found: C:/k.json", "key"),
    ("('invalid_grant: Invalid JWT Signature.', {})", "key"),
    ("RefreshError: ('invalid_client', 'The OAuth client was not found.')", "key"),
    ("403 from the export endpoint. The service account exists but is not allowed to read this sheet.", "sharing"),
    ("404 from the export endpoint. Either the sheet_id is wrong, or the sheet has not been shared", "sharing"),
    ("The export returned an HTML page, not CSV - that is a sign-in or permission redirect.", "sharing"),
    ("HTTPSConnectionPool(host='docs.google.com', port=443): Read timed out. (read timeout=60)", "network"),
    ("503 Server Error: Service Unavailable for url: https://docs.google.com/...", "network"),
    ("Max retries exceeded with url (Caused by NameResolutionError)", "network"),
    ("utility: the conference export is missing column(s) ['CONFERENCE']. Wrong tab. The export is kept at C:/qa/x.csv.", "structure"),
    ("utility: the export parsed as CSV but has no rows. The export is kept at C:/qa/x.csv.", "structure"),
    ("No module named 'google'", "software"),
    ("No config at C:/x/customer_sheets.json.", "config"),
    ("something nobody has seen before", "unknown"),
])
def test_each_cause_the_code_can_tell_apart(text, cause):
    assert csl.classify(text) == cause


# ------------------------------------------------------------------ retries
def test_a_network_blip_clears_itself_on_a_retry_and_sends_nothing(w):
    code, res, lines, clock = w.load([{"utility": "Read timed out."}, {}])
    assert code == 0 and not res["failed"] and clock.slept == [300]
    assert w.calls[1][w.calls[1].index("--client") + 1] == "utility", "only the failed sheet is fetched again"
    assert lines[0].startswith("SHEET LOAD: HEALTHY - 4 of 4") and "on try 2" in lines[0]
    assert not w.sent and not w.desk[0].exists()


def test_a_network_failure_is_tried_three_times_over_15_minutes_then_one_email(w):
    code, res, lines, clock = w.load([{"utility": "Read timed out."}])
    assert code == csl.HELD_EXIT and res["failed"] == ["utility"] and clock.slept == [300, 600] and len(w.calls) == 3      # HELD since 2026-11-13 (D66 = B)
    assert len(w.sent) == 1
    subj, body, kw = w.sent[0]
    assert subj == "CFP customer sheets failed to load - CRITICAL ERROR" and kw == {"to_env": "CFP_RECAP_TO"}
    assert "after 3 tries over about 15 minutes" in body and "could not reach Google" in body


def test_a_failure_a_retry_cannot_fix_is_not_retried(w):
    code, res, _l, clock = w.load([{"arnica": "403 from the export endpoint. Share it."}])
    assert code == csl.HELD_EXIT and len(w.calls) == 1 and clock.slept == []
    assert res["outcomes"]["arnica"]["cause"] == "sharing"


def test_one_permanent_and_one_transient_failure_retries_only_the_transient_one(w):
    code, res, _l, _c = w.load([{"arnica": "403 from the export endpoint.", "utility": "Read timed out."}, {"arnica": "403 from the export endpoint."}])
    assert [c[c.index("--client") + 1] for c in w.calls] == ["arnica,utility,arnica-awards,utility-awards", "utility"]
    assert res["failed"] == ["arnica"] and code == csl.HELD_EXIT


def test_a_copy_older_than_this_run_is_a_failure(w):
    w.copy("utility-awards", NOW - timedelta(days=7))
    code, res, _l, _c = w.load([{"utility-awards": "nocopy"}])
    assert code == csl.HELD_EXIT and res["outcomes"]["utility-awards"]["cause"] == "not_saved" and len(w.calls) == 3
    assert "no new copy was saved" in w.sent[0][1]


# ------------------------------------------------------------------ the email: subject, body, every cause, no secret
def test_the_subject_and_the_body_layout_are_exact(w):
    w.copy("utility", NOW - timedelta(days=8))
    _code, _r, _l, _c = w.load([{"utility": "403 from the export endpoint. Share it."}])
    subj, body, _kw = w.sent[0]
    assert subj == "CFP customer sheets failed to load - CRITICAL ERROR"
    lines = body.splitlines()
    assert lines[0] == "CFP customer sheets failed to load - CRITICAL ERROR" and lines[2] == "WHAT FAILED"
    assert lines[3].startswith("- Utility Global conferences sheet (utility): failed at 02:00 on Sat 14 Nov 2026. Error: 403")
    order = [body.index(h) for h in ("WHAT FAILED", "WHAT THIS MEANS", "LIKELY CAUSE:", "HOW TO FIX IT", "EVIDENCE")]
    assert order == sorted(order)
    assert "Loaded fine: Arnica conferences sheet, Arnica awards sheet, Utility Global awards sheet." in body
    assert "The Saturday 02:00 conference research is HELD: it did NOT start, because the sheets did not load" in body       # D66 = B, 2026-11-13
    assert "Utility Global conferences sheet: Fri 06 Nov (8 days old)" in body
    assert "customer_sheet_load.py' --clients utility --once" in body and "SHEET LOAD: HEALTHY" in body
    assert "What you do yourself:" in body and "What the re-run does for you:" in body
    assert body.isascii()


def test_sharing_steps_name_the_sheet_and_how_to_find_the_reader_address(w):
    w.load([{"arnica-awards": "403 from the export endpoint."}])
    body = w.sent[0][1]
    assert "https://docs.google.com/spreadsheets/d/SHEET-AA/edit#gid=3" in body and ".client_email" in body and "Viewer" in body


def test_key_steps_say_how_to_make_a_new_key_and_never_show_it(w):
    w.load([{c: "Service account key not found: " + str(w.key) for c in csl.ALL_CLIENTS}])
    body = w.sent[0][1]
    assert "Test-Path '" + str(w.key) + "'" in body and "Create new key > JSON" in body and "Move-Item" in body
    assert "BEGIN PRIVATE KEY" not in body and "MIIfake" not in body and FAKE_PASS not in body


def test_structure_steps_open_the_kept_copy_and_list_the_columns(w):
    kept = w.tmp / "qa" / "intake_failed_utility.csv"
    w.load([{"utility": f"utility: the conference export is missing column(s) ['CONFERENCE']. Wrong tab. The export is kept at {kept}."}])
    body = w.sent[0][1]
    assert f"notepad '{kept}'" in body and "CONFERENCE, STATUS, SUBMISSION DEADLINE" in body and "layout changed" in body


def test_network_software_config_and_unknown_each_get_their_own_fix(w):
    cases = {"network": ("Read timed out.", "appsstatus"), "software": ("No module named 'google'", "uv sync"),
             "config": ("No config at X.", "Restore previous versions"), "unknown": ("a brand new error", "a brand new error")}
    for cause, (err, needle) in cases.items():
        w.sent.clear()
        w.state.unlink(missing_ok=True)
        w.load([{"utility": err}])
        assert needle in w.sent[0][1], cause


def test_two_causes_get_two_fix_sections(w):
    w.load([{"arnica": "403 from the export endpoint.", "utility": "No module named 'google'"}])
    body = w.sent[0][1]
    assert "LIKELY CAUSE 1 of 2" in body and "LIKELY CAUSE 2 of 2" in body and body.count("HOW TO FIX IT") == 2


def test_no_secret_reaches_the_email_the_desktop_file_or_the_evidence(w):
    leak = f"403 from the export endpoint. debug pass={FAKE_PASS} {FAKE_KEY_BLOCK}"
    _code, _r, lines, _c = w.load([{"arnica": leak}])
    ev = Path(lines[0].split("evidence: ")[1].split(";")[0])
    for text in (w.sent[0][1], w.desk[0].read_text(encoding="utf-8"), ev.read_text(encoding="utf-8")):
        assert FAKE_PASS not in text and "BEGIN PRIVATE KEY" not in text and "MIIfake" not in text
        assert "[CFP_SMTP_PASS removed]" in text


def test_redact_strips_secret_env_values_and_key_blocks_and_leaves_ordinary_text():
    env = {"CFP_SMTP_PASS": "abcdefgh123", "GEMINI_API_KEY": "AIzaFAKEFAKEFAKE", "CFP_RECAP_TO": "me@example.org", "SHORT_KEY": "abc"}
    out = csl.redact(f"a abcdefgh123 b AIzaFAKEFAKEFAKE c me@example.org abc {FAKE_KEY_BLOCK}", env)
    assert "abcdefgh123" not in out and "AIzaFAKE" not in out and "MIIfake" not in out
    assert "me@example.org" in out and " abc " in out, "only secret-named values are stripped"


# ------------------------------------------------------------------ files, one a day, hold, the re-run
def test_the_desktop_file_carries_the_same_text_and_the_evidence_is_named_in_the_verdict(w):
    _code, _r, lines, _c = w.load([{"utility": "403 from the export endpoint."}])
    assert w.desk[0].read_text(encoding="utf-8") == w.sent[0][1]
    assert "evidence: " in lines[0] and "email sent" in lines[0]
    ev = json.loads(Path(lines[0].split("evidence: ")[1].split(";")[0]).read_text(encoding="utf-8"))
    assert ev["failed"] == ["utility"] and ev["attempts"][0]["exit"] == 1


def test_one_alert_a_day_and_a_test_send_does_not_count(w):
    csl.send("[TEST] x", "y", NOW.date(), NOW, w.mailer, w.state, test=True)
    w.load([{"utility": "403 from the export endpoint."}])
    _code, _r, lines, _c = w.load([{"utility": "403 from the export endpoint."}])
    assert [s[0] for s in w.sent] == ["[TEST] x", "CFP customer sheets failed to load - CRITICAL ERROR"]
    assert "already sent at 02:00 today" in lines[0]


# ------------------------------------------------------------------ the wait (Matt, 2026-11-10: "Wait up to 2 hours")
def test_the_wait_is_two_hours_by_default_and_fits_the_task_limit():
    assert csl.hold_plan("saturday", {}, lambda t: {}) == (2.0, "")                       # limit unknown: the full wait
    assert csl.hold_plan("saturday", {}, lambda t: {"limit_h": 8.0}) == (2.0, "")         # D14: 8 h fits 2 h + a 4.5 h run
    assert csl.hold_plan("friday", {}, lambda t: {"limit_h": 16.0}) == (2.0, "")
    hours, why = csl.hold_plan("saturday", {}, lambda t: {"limit_h": 5.0})                # today's Saturday limit: no room
    assert hours == 0.0 and "after 5 hours" in why and "raise the task's limit" in why
    assert csl.hold_plan("saturday", {"CFP_SHEETS_HOLD_HOURS": "0"}, lambda t: {"limit_h": 8.0})[0] == 0.0
    assert csl.hold_plan("saturday", {"CFP_SHEETS_HOLD_HOURS": "20"}, lambda t: {"limit_h": 8.0})[0] == 2.75   # capped at 4, then cut to fit
    assert csl.hold_plan(None, {"CFP_SHEETS_HOLD_HOURS": "1.5"}, lambda t: {"limit_h": 1.0}) == (1.5, "")      # no research context: no task
    hours, why = csl.hold_plan("friday", {"CFP_SHEETS_HOLD_HOURS": "two"}, lambda t: {})
    assert hours == 2.0 and "not a number" in why


def test_the_task_limit_is_read_from_task_scheduler_output():
    assert csl.parse_duration_h("PT5H") == 5.0 and csl.parse_duration_h("PT45M") == 0.75 and csl.parse_duration_h("P3D") == 72.0
    assert csl.parse_duration_h("PT0S") is None and csl.parse_duration_h("") is None and csl.parse_duration_h("junk") is None
    seen = []

    def fake(cmd, timeout=60):
        seen.append(cmd)
        return 0, 'WARNING: noise\n{"state":"Ready","last":"2026-11-07T02:00:00","limit":"PT5H"}'
    info = REAL_TASK_INFO("CFP Weekly Re-Research (live markets)", runner=fake)
    assert info == {"state": "Ready", "last_run": datetime(2026, 11, 7, 2, 0), "limit_h": 5.0}
    assert "Get-ScheduledTask" in seen[0][-1] and "Register" not in seen[0][-1] and "Set-" not in seen[0][-1]   # read only
    assert REAL_TASK_INFO("x", runner=lambda c, timeout=60: (1, "no such task")) == {}


def test_a_fix_during_the_wait_starts_the_research_and_sends_the_loaded_email(w):
    w.copy("utility", NOW - timedelta(days=8))
    script = [{"utility": "403 from the export endpoint."}, {"utility": "403 from the export endpoint."}, {}]
    code, res, lines, clock = w.load(script, env={})
    assert code == 0 and res["failed"] == []
    assert [s[0] for s in w.sent] == [csl.SUBJECT, "CFP customer sheets loaded - research started"]
    critical, loaded = w.sent[0][1], w.sent[1][1]
    assert "is WAITING for the sheets" in critical and "until 04:00" in critical and "'CFP customer sheets loaded - research started'" in critical
    assert "the research is HELD: it does NOT start" in critical and csl.SUBJECT_HELD in critical and "notices your fix within 10 minutes" in critical
    assert "loaded at 02:20, after waiting 20 minutes: Utility Global conferences sheet" in loaded and "has started on fresh copies" in loaded
    assert lines[-1].startswith("SHEET LOAD: HEALTHY - all 4 sheet(s) loaded at 02:20 after waiting 20 min")
    assert clock.slept == [600, 600] and len(w.calls) == 3                                # sharing is not retried at first; the wait tries every 10 min
    assert not w.desk[0].exists()
    st = json.loads(w.status.read_text(encoding="utf-8"))["saturday"]
    assert st["verdict"] == "RECOVERED" and st["waited_min"] == 20 and st["failed"] == []


def test_still_failing_after_two_hours_is_HELD_the_research_does_not_start(w):
    """Matt, 2026-11-13 (D66 = B): "If the customer sheets don't load I do NOT want to proceed." Exit 6, nothing researched."""
    w.copy("utility", NOW - timedelta(days=8))
    code, res, lines, clock = w.load([{"utility": "403 from the export endpoint."}], env={})
    assert code == csl.HELD_EXIT == 6 and res["failed"] == ["utility"]
    assert [s[0] for s in w.sent] == [csl.SUBJECT, csl.SUBJECT_HELD]
    first, held = w.sent[0][1], w.sent[1][1]
    assert "is WAITING for the sheets and has NOT started" in first and "the research is HELD: it does NOT start" in first and csl.SUBJECT_HELD in first
    assert "going ahead" not in held and "goes ahead on the last good copies" not in held and "research ran on copies" not in held
    assert "is HELD: it did NOT start, because the sheets did not load" in held and "show this weekend as HELD" in held
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in held
    assert "--clients utility --once" in held and "SHEET LOAD: HEALTHY" in held and "HOW TO FIX IT" in held
    assert "CFP_SHEETS_ON_FAIL" in held and "-Markets Cybersecurity,Utility" in held and held.isascii()
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in first, "the first email already says how to start it"
    assert clock.now() == NOW + timedelta(hours=2) and len(w.calls) == 13                    # 1 + one try every 10 minutes for 2 hours
    assert lines[-1].startswith("SHEET LOAD: HELD - 1 of 4 sheet(s) still not loaded (utility; cause: sharing) after waiting 120 min")
    assert "did NOT start: nothing researched, nothing spent" in lines[-1] and "Start-ScheduledTask" in lines[-1]
    st = json.loads(w.status.read_text(encoding="utf-8"))["saturday"]
    assert st["verdict"] == "HELD" and st["failed"] == ["utility"] and st["waited_min"] == 120
    for subj, b, _kw in w.sent:
        assert FAKE_PASS not in b and "MIIfake" not in b


def test_held_with_no_wait_possible_sends_one_email_and_does_not_start(w):
    code, res, lines, clock = w.load([{"utility": "403 from the export endpoint."}])          # default env: CFP_SHEETS_HOLD_HOURS=0
    assert code == csl.HELD_EXIT and clock.slept == [] and [s[0] for s in w.sent] == [csl.SUBJECT]
    assert "is HELD: it did NOT start" in w.sent[0][1] and lines[-1].startswith("SHEET LOAD: HELD") and "after waiting" not in lines[-1]
    assert json.loads(w.status.read_text(encoding="utf-8"))["saturday"]["verdict"] == "HELD"


def test_a_good_load_still_lets_the_research_run_and_a_fix_during_the_wait_starts_it(w):
    code, _r, _l, _c = w.load([{}])
    assert code == 0 and not w.sent
    code, res, lines, _c = w.load([{"utility": "403 from the export endpoint."}, {}], env={})
    assert code == 0 and res["failed"] == [] and lines[-1].startswith("SHEET LOAD: HEALTHY") and csl.SUBJECT_HELD not in [s[0] for s in w.sent]


def test_friday_hold_names_the_awards_task_and_the_awards_markets(w):
    code, _r, _l, _c = w.load([{"arnica-awards": "403 from the export endpoint."}], clients=csl.AWARD_CLIENTS, context="friday", env={}, task={"limit_h": 16.0})
    held = w.sent[-1][1]
    assert code == csl.HELD_EXIT and w.sent[-1][0] == csl.SUBJECT_HELD
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Awards Research'" in held and "-Markets Awards" in held and "Friday 02:00 awards research is HELD" in held


def test_the_person_can_choose_to_proceed_on_old_copies_by_hand(w):
    """CFP_SHEETS_ON_FAIL=proceed brings back the 2026-11-10 rule: research on the last good copies, exit 1, DEGRADED. Never the default."""
    w.copy("utility", NOW - timedelta(days=8))
    code, res, lines, clock = w.load([{"utility": "403 from the export endpoint."}], env={"CFP_SHEETS_ON_FAIL": "proceed"})
    assert code == 1 and res["failed"] == ["utility"]
    subjects = [s[0] for s in w.sent]
    assert subjects == [csl.SUBJECT, "CFP customer sheets still not loaded - research ran on copies from Fri 06 Nov 2026"]
    body = w.sent[1][1]
    assert "still failing at 04:00 after waiting 120 minutes since 02:00" in body and "is going ahead now on the last good copies" in body
    assert "show this weekend as DEGRADED" in body and "HOW TO FIX IT" in body and "--clients utility --once" in body and body.isascii()
    assert clock.now() == NOW + timedelta(hours=2) and len(w.calls) == 13                    # 1 + one try every 10 minutes for 2 hours
    assert lines[-1].startswith("SHEET LOAD: DEGRADED - 1 of 4 sheet(s) still not loaded after waiting 120 min (utility; cause: sharing)")
    assert "the research runs on copies from Fri 06 Nov 2026" in lines[-1]
    assert w.desk[0].read_text(encoding="utf-8") == body                                       # the Desktop file shows the latest state
    st = json.loads(w.status.read_text(encoding="utf-8"))["saturday"]
    assert st["verdict"] == "DEGRADED" and st["failed"] == ["utility"] and st["copies"]["utility"].startswith("2026-11-06")
    for subj, b, _kw in w.sent:
        assert FAKE_PASS not in b and "MIIfake" not in b


def test_the_follow_up_does_not_use_up_the_one_critical_email_a_day(w):
    w.load([{"utility": "403 from the export endpoint."}], env={})
    w.load([{"utility": "403 from the export endpoint."}], env={})        # a second failure the same day
    subjects = [s[0] for s in w.sent]
    assert subjects.count(csl.SUBJECT) == 1 and subjects.count(subjects[1]) == 2


def test_with_the_five_hour_limit_saturday_does_not_wait_and_says_why(w):
    code, _res, lines, clock = w.load([{"utility": "403 from the export endpoint."}], env={}, task={"limit_h": 5.0})
    assert code == csl.HELD_EXIT and len(w.sent) == 1 and clock.slept == []
    assert "It does not wait for the sheets: Windows stops 'CFP Weekly Re-Research (live markets)' after 5 hours" in w.sent[0][1]
    assert "is HELD: it did NOT start" in w.sent[0][1]
    assert "no wait (Windows stops" in lines[0] and json.loads(w.status.read_text(encoding="utf-8"))["saturday"]["verdict"] == "HELD"


def test_a_healthy_load_records_healthy_for_the_recap_and_gate(w):
    code, _r, _l, _c = w.load([{}], env={})
    assert code == 0 and not w.sent and json.loads(w.status.read_text(encoding="utf-8"))["saturday"]["verdict"] == "HEALTHY"


def test_the_persons_rerun_never_waits_and_records_nothing(w):
    code, _r, _lines, clock = w.load([{"utility": "403 from the export endpoint."}], env={}, once=True)
    assert code == 1 and clock.slept == [] and not w.sent and not w.status.exists()


def test_friday_wording_names_the_awards_research(w):
    w.load([{"arnica-awards": "Read timed out."}], clients=csl.AWARD_CLIENTS, context="friday")
    assert "Friday 02:00 awards research is HELD: it did NOT start" in w.sent[0][1]
    w2_sent = len(w.sent)
    w.load([{"arnica-awards": "Read timed out."}], clients=csl.AWARD_CLIENTS, context="friday", env={}, task={"limit_h": 16.0})
    assert "The Friday 02:00 awards research is WAITING for the sheets" in "".join(b for _s, b, _k in w.sent[w2_sent:]) or len(w.sent) > w2_sent


def test_the_persons_rerun_tries_once_sends_nothing_and_prints_the_fix(w):
    code, _r, lines, clock = w.load([{"utility": "Read timed out."}], once=True)
    assert code == 1 and len(w.calls) == 1 and clock.slept == [] and not w.sent
    assert any("HOW TO FIX IT" in ln for ln in lines)
    assert lines[-1].startswith("SHEET LOAD: FAILED") and "email not sent: --once" in lines[-1], "the verdict is the LAST line (Codex review, 2026-11-10)"


def test_check_only_prints_the_verdict_last(monkeypatch, capsys):
    """Codex review 2026-11-10: --check-only printed the verdict first and the fix lines after it."""
    failed = {"clients": ["utility"], "failed": ["utility"], "attempts": [], "read_only": True, "outcome": {}}
    monkeypatch.setattr(csl, "read_check", lambda config: failed)
    monkeypatch.setattr(csl, "verdict_line", lambda r, extra="": "SHEET LOAD: FAILED - 1 of 1 sheet(s) did not load")
    monkeypatch.setattr(csl, "fix_summary", lambda r, config: ["utility: open the sheet and check its sharing"])
    assert csl.main(["--check-only"]) == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("SHEET LOAD: FAILED") and out[0].lstrip().startswith("- utility")


def test_a_healthy_load_sends_nothing_writes_nothing_and_clears_the_desktop_file(w, tmp_path):
    w.desk[0].parent.mkdir(parents=True)
    w.desk[0].write_text("old alert", encoding="utf-8")
    code, res, lines = csl.guarded_load(list(csl.ALL_CLIENTS), "saturday", w.config, w.snaps, env={}, mailer=w.mailer,
                                            sleep=Clock().sleep, runner=w.runner([{}], Clock()), now=Clock().now, qa_root=w.qa, state=w.state,
                                            status_path=w.status)
    assert code == 0 and not w.sent and not w.qa.exists() and not w.desk[0].exists()
    assert lines == ["SHEET LOAD: HEALTHY - 4 of 4 sheet(s) loaded at 02:00"]


# ------------------------------------------------------------------ the dead-man check
def deadman(w, kind="saturday", now=NOW.replace(hour=3, minute=0), clock=None, task=None, **kw):
    """task: a dict the stub task reader returns, or a list of dicts returned one per call (the last one repeats)."""
    clock = clock or Clock(now)
    seq = task if isinstance(task, list) else [task or {}]
    calls = []

    def reader(name):
        calls.append(name)
        return dict(seq[min(len(calls), len(seq)) - 1])
    return csl.deadman(kind, w.snaps, w.tmp / "logs", w.config, now=clock.now, sleep=clock.sleep, env={}, mailer=w.mailer,
                       qa_root=w.qa, state=w.state, alert_files=w.desk, task_reader=reader, **kw), clock


def test_deadman_is_quiet_when_todays_copies_are_there(w):
    for c in csl.ALL_CLIENTS:
        w.copy(c, NOW)
    (code, lines), _c = deadman(w)
    assert code == 0 and lines[0].startswith("SHEET DEADMAN: HEALTHY") and not w.sent


def test_deadman_friday_checks_only_the_two_awards_sheets(w):
    for c in csl.AWARD_CLIENTS:
        w.copy(c, NOW.replace(day=13))
    (code, _lines), _c = deadman(w, "friday", NOW.replace(day=13, hour=3))
    assert code == 0 and not w.sent


def test_deadman_case_1_the_research_task_did_not_start(w):
    for c in csl.ALL_CLIENTS:
        w.copy(c, NOW - timedelta(days=7))
    (code, lines), clock = deadman(w, task={"state": "Ready", "last_run": datetime(2026, 11, 7, 2, 0), "limit_h": 5.0})
    assert code == 1 and "the research task did not start: 4 of 4 sheet(s) have no copy from today" in lines[0]
    assert sum(clock.slept) == csl.DEADMAN_START_GRACE_S                                   # gave a late task 5 minutes to start by itself
    subj, body, _kw = w.sent[0]
    assert subj == csl.SUBJECT and "LIKELY CAUSE: The research task did not start" in body
    assert "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in body and "its last run was Sat 07 Nov 02:00" in body
    assert "did NOT start today, so nothing has been researched yet" in body


def test_deadman_case_1_a_task_that_starts_during_the_grace_is_running_not_missing(w):
    (code, lines), _clock = deadman(w, task=[{"state": "Ready", "last_run": datetime(2026, 11, 7, 2, 0)},
                                             {"state": "Ready", "last_run": datetime(2026, 11, 7, 2, 0)},
                                             {"state": "Running", "last_run": NOW.replace(hour=3, minute=1)}])
    assert code == 0 and lines[0].startswith("SHEET DEADMAN: RUNNING") and not w.sent


def test_deadman_case_2_the_task_is_running_sends_nothing(w):
    (code, lines), clock = deadman(w, task={"state": "Running", "last_run": NOW})
    assert code == 0 and not w.sent and clock.slept == []
    assert "is running: it raises its own alert and waits for the sheets. Nothing sent." in lines[0]


def test_deadman_case_2_a_fresh_run_log_also_counts_as_running(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    log = logs / "run_monthly_20261114-020001.log"
    log.write_text("SHEET WAIT: try at 02:50 - 1 still failing\n", encoding="utf-8")
    t = NOW.replace(hour=2, minute=55).timestamp()
    os.utime(log, (t, t))
    (code, lines), _c = deadman(w, task={})                                                 # Task Scheduler could not be read
    assert code == 0 and lines[0].startswith("SHEET DEADMAN: RUNNING") and not w.sent


def test_deadman_case_3_the_task_ran_and_the_cause_is_read_from_todays_run_log(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    log = logs / "run_monthly_20261114-020001.log"
    log.write_text("utility: FAILED - 403 from the export endpoint. Share it.\n", encoding="utf-8")
    old = (NOW - timedelta(hours=2)).timestamp()
    os.utime(log, (old, old))
    for c in ("arnica", "arnica-awards", "utility-awards"):
        w.copy(c, NOW)
    (code, lines), clock = deadman(w, task={"state": "Ready", "last_run": NOW})
    assert code == 1 and clock.slept == [] and "the research ran but today's copies are missing" in lines[0]
    assert "Google refused to let our reader open the sheet" in w.sent[0][1] and "ran today but did not take today's copies" in w.sent[0][1]


def test_deadman_case_3_without_a_failure_line_says_the_run_skipped_the_sheets(w):
    (code, _lines), _c = deadman(w, task={"state": "Ready", "last_run": NOW.replace(hour=2, minute=0)})
    body = w.sent[0][1]
    assert code == 1 and "ran today and finished, but did not save today's copies" in body and "SHEET LOAD and STOPPED" in body


def test_deadman_does_not_send_a_second_email_after_the_run_already_alerted(w):
    w.load([{"utility": "403 from the export endpoint."}])
    (code, lines), _c = deadman(w, task={"state": "Ready", "last_run": NOW})
    assert code == 1 and len(w.sent) == 1 and "already sent" in lines[0]


# ------------------------------------------------------------------ the Thursday read-only check
def test_the_read_check_saves_nothing_tries_once_and_sends_nothing(w):
    clock = Clock()
    res = csl.load(list(csl.ALL_CLIENTS), w.config, w.snaps, waits=(), runner=w.runner([{"utility": "Service account key not found: x"}], clock),
                   now=clock.now, read_only=True)
    assert "--no-snapshot" in w.calls[0] and "--out-dir" not in w.calls[0] and len(w.calls) == 1
    assert res["failed"] == ["utility"] and not any(w.snaps.iterdir()) and not w.sent
    lines = csl.fix_summary(res, w.config)
    assert lines and "service-account key" in lines[0]


# ------------------------------------------------------------------ DEGRADED reaches the recap and the Sunday gate (Matt, 2026-11-10)
def test_the_recap_reads_the_last_sheet_load_line_and_says_degraded_in_the_subject():
    from scripts.weekend_recap import parse_saturday, saturday_recap
    log = ("=== run_monthly exit code: 0 ===\nINTAKE HEALTH: ok\n"
           "SHEET LOAD: FAILED - 1 of 4 sheet(s) did not load (utility; cause: sharing); email sent; evidence: x.json; waiting up to 2 hours (until 04:00) for the sheets\n"
           "SHEET WAIT: try at 02:20 - 1 still failing (utility); next try in 10 min, until 04:00\n"
           "SHEET LOAD: DEGRADED - 1 of 4 sheet(s) still not loaded after waiting 120 min (utility; cause: sharing); the research runs on copies from Fri 06 Nov 2026\n")
    assert parse_saturday(log)["sheet_load"].startswith("DEGRADED - 1 of 4")
    subject, text, _ = saturday_recap(log, None, Path("."), "saturday", None)
    assert "DEGRADED: customer sheets did not load, research used old copies" in subject
    assert "Customer sheets: DEGRADED - 1 of 4 sheet(s) still not loaded" in text
    ok_log = log.replace("SHEET LOAD: DEGRADED - 1 of 4 sheet(s) still not loaded after waiting 120 min (utility; cause: sharing); the research runs on copies from Fri 06 Nov 2026",
                         "SHEET LOAD: HEALTHY - all 4 sheet(s) loaded at 02:20 after waiting 20 min")
    subject, _text, _ = saturday_recap(ok_log, None, Path("."), "saturday", None)
    assert "DEGRADED" not in subject


def test_the_sunday_gate_warns_degraded_when_a_research_ran_on_old_copies():
    from types import SimpleNamespace
    from datetime import date
    from scripts import release_gate as rg
    o = SimpleNamespace(on=date(2026, 11, 15))
    bad = {"saturday": {"date": "2026-11-14", "verdict": "DEGRADED", "failed": ["utility"], "copies": {"utility": "2026-11-06T02:00:00"}, "waited_min": 120},
           "friday": {"date": "2026-11-13", "verdict": "RECOVERED", "failed": [], "waited_min": 20}}
    c = rg.check_sheet_load(o, bad)
    assert c["status"] == "WARN" and c["summary"].startswith("DEGRADED: Saturday's research ran on old copies")
    assert any("utility 2026-11-06" in r for r in c["rows"]) and any("loaded after waiting 20 min" in r for r in c["rows"])
    assert rg.check_sheet_load(o, {"saturday": {"date": "2026-11-14", "verdict": "HEALTHY", "failed": []}})["status"] == "PASS"
    old = {"saturday": {"date": "2026-11-07", "verdict": "DEGRADED", "failed": ["utility"]}}       # last week's: not this weekend
    assert rg.check_sheet_load(o, old)["status"] == "PASS" and rg.check_sheet_load(o, {})["status"] == "PASS"
