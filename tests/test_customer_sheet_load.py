"""scripts/customer_sheet_load.py: Matt's CRITICAL alert when the customer sheets do not load (2026-11-09).

Every fetch is faked (no network), every email goes to a stub (tests/conftest.py also removes the mail settings), and every file lands in
tmp_path. Covers: each cause the code can tell apart, the retries (only what can clear by itself), the exact subject and body, no secret in
anything written or sent, one alert a day, the hold switch, the person's re-run, the dead-man check and the Thursday read-only check. And
the inversion: a healthy load sends nothing and writes nothing."""
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

    def load(self, script, clients=csl.ALL_CLIENTS, env=None, once=False, context="saturday", clock=None):
        clock = clock or Clock()
        return csl.guarded_load(list(clients), context, self.config, self.snaps, once=once, env=env or {}, mailer=self.mailer,
                                sleep=clock.sleep, runner=self.runner(script, clock), now=clock.now, qa_root=self.qa,
                                state=self.state, alert_files=self.desk) + (clock,)


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(csl.fcs, "alert_paths", lambda: [tmp_path / "desk" / "CUSTOMER-SHEET-FETCH-FAILED.txt"])
    monkeypatch.setenv("CFP_SMTP_PASS", FAKE_PASS)          # present in the environment, so redact() has something to strip
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
    assert code == 1 and res["failed"] == ["utility"] and clock.slept == [300, 600] and len(w.calls) == 3
    assert len(w.sent) == 1
    subj, body, kw = w.sent[0]
    assert subj == "CFP customer sheets failed to load - CRITICAL ERROR" and kw == {"to_env": "CFP_RECAP_TO"}
    assert "after 3 tries over about 15 minutes" in body and "could not reach Google" in body


def test_a_failure_a_retry_cannot_fix_is_not_retried(w):
    code, res, _l, clock = w.load([{"arnica": "403 from the export endpoint. Share it."}])
    assert code == 1 and len(w.calls) == 1 and clock.slept == []
    assert res["outcomes"]["arnica"]["cause"] == "sharing"


def test_one_permanent_and_one_transient_failure_retries_only_the_transient_one(w):
    code, res, _l, _c = w.load([{"arnica": "403 from the export endpoint.", "utility": "Read timed out."}, {"arnica": "403 from the export endpoint."}])
    assert [c[c.index("--client") + 1] for c in w.calls] == ["arnica,utility,arnica-awards,utility-awards", "utility"]
    assert res["failed"] == ["arnica"] and code == 1


def test_a_copy_older_than_this_run_is_a_failure(w):
    w.copy("utility-awards", NOW - timedelta(days=7))
    code, res, _l, _c = w.load([{"utility-awards": "nocopy"}])
    assert code == 1 and res["outcomes"]["utility-awards"]["cause"] == "not_saved" and len(w.calls) == 3
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
    assert "The Saturday 02:00 conference research goes ahead with the last good copy" in body
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


def test_hold_switch_on_exits_6_and_says_research_waits(w):
    code, _r, lines, _c = w.load([{"utility": "403 from the export endpoint."}], env={"CFP_SHEETS_HOLD_RESEARCH": "1"})
    body = w.sent[0][1]
    assert code == 6 and "RESEARCH HELD" in lines[0]
    assert "has NOT started and waits for you" in body and "Start-ScheduledTask -TaskName 'CFP Weekly Re-Research (live markets)'" in body


def test_hold_switch_off_never_stops_the_research(w):
    code, _r, _l, _c = w.load([{"utility": "403 from the export endpoint."}], env={"CFP_SHEETS_HOLD_RESEARCH": "0"})
    assert code == 1 and "goes ahead with the last good copy" in w.sent[0][1]


def test_friday_wording_names_the_awards_research(w):
    w.load([{"arnica-awards": "Read timed out."}], clients=csl.AWARD_CLIENTS, context="friday")
    assert "Friday 02:00 awards research goes ahead" in w.sent[0][1]


def test_the_persons_rerun_tries_once_sends_nothing_and_prints_the_fix(w):
    code, _r, lines, clock = w.load([{"utility": "Read timed out."}], once=True)
    assert code == 1 and len(w.calls) == 1 and clock.slept == [] and not w.sent
    assert "email not sent: --once" in lines[0] and any("HOW TO FIX IT" in ln for ln in lines)


def test_a_healthy_load_sends_nothing_writes_nothing_and_clears_the_desktop_file(w, tmp_path):
    w.desk[0].parent.mkdir(parents=True)
    w.desk[0].write_text("old alert", encoding="utf-8")
    code, res, lines = csl.guarded_load(list(csl.ALL_CLIENTS), "saturday", w.config, w.snaps, env={}, mailer=w.mailer,
                                            sleep=Clock().sleep, runner=w.runner([{}], Clock()), now=Clock().now, qa_root=w.qa, state=w.state)
    assert code == 0 and not w.sent and not w.qa.exists() and not w.desk[0].exists()
    assert lines == ["SHEET LOAD: HEALTHY - 4 of 4 sheet(s) loaded at 02:00"]


# ------------------------------------------------------------------ the dead-man check
def deadman(w, kind="saturday", now=NOW.replace(hour=3, minute=0), clock=None, **kw):
    clock = clock or Clock(now)
    return csl.deadman(kind, w.snaps, w.tmp / "logs", w.config, now=clock.now, sleep=clock.sleep, env={}, mailer=w.mailer,
                       qa_root=w.qa, state=w.state, alert_files=w.desk, **kw), clock


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


def test_deadman_when_the_job_never_ran_sends_the_critical_email(w):
    for c in csl.ALL_CLIENTS:
        w.copy(c, NOW - timedelta(days=7))
    (code, lines), _c = deadman(w)
    assert code == 1 and "4 of 4 sheet(s) have no copy from today" in lines[0]
    subj, body, _kw = w.sent[0]
    assert subj == csl.SUBJECT and "did not take today's copies" in body and "Get-ScheduledTaskInfo -TaskName 'CFP Weekly Re-Research (live markets)'" in body
    assert "no run log for today" in body


def test_deadman_reads_the_cause_from_todays_run_log(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    log = logs / "run_monthly_20261114-020001.log"
    log.write_text("utility: FAILED - 403 from the export endpoint. Share it.\n", encoding="utf-8")
    old = (NOW - timedelta(hours=2)).timestamp()
    os.utime(log, (old, old))
    for c in ("arnica", "arnica-awards", "utility-awards"):
        w.copy(c, NOW)
    (code, _lines), clock = deadman(w)
    assert code == 1 and clock.slept == [] and "Google refused to let our reader open the sheet" in w.sent[0][1]


def test_deadman_waits_for_a_run_that_is_still_going_then_is_quiet(w):
    logs = w.tmp / "logs"
    logs.mkdir()
    log = logs / "run_monthly_20261114-030001.log"
    log.write_text("started\n", encoding="utf-8")
    t = NOW.replace(hour=3).timestamp()
    os.utime(log, (t, t))
    clock = Clock(NOW.replace(hour=3, minute=2))
    real_sleep = clock.sleep

    def sleep_then_copy(s):
        real_sleep(s)
        for c in csl.ALL_CLIENTS:
            w.copy(c, clock.now())
    clock.sleep = sleep_then_copy
    (code, _lines), _c = deadman(w, clock=clock)
    assert code == 0 and not w.sent and len(clock.slept) == 1


def test_deadman_does_not_send_a_second_email_after_the_run_already_alerted(w):
    w.load([{"utility": "403 from the export endpoint."}])
    (code, lines), _c = deadman(w)
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
