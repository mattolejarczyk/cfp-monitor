"""Intake retries what might pass next time, stops on what cannot - and says WHY either way.

Two defects, found 2026-09-16 while wiring up the service account:

1. Every failure was retried three times, ~100 seconds, including a missing library, a missing
   key and an unshared sheet. None of those changes between attempts.
2. The recorded reason was the fetch's LAST line of output, which with --alert is always
   "alert written: ...". So intake_status.json said a failure happened and never said what it was.

The inversion matters as much as the fix: a transient failure must still be retried, and an
unrecognised one must be treated as transient, because giving up early costs a week's intake.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("wi", ROOT / "scripts" / "weekly_intake.py")
wi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wi)

ALERT = "\nalert written: C:\\Users\\x\\Desktop\\CUSTOMER-SHEET-FETCH-FAILED.txt"


def _fetch_all(monkeypatch, tmp_path, outputs):
    """Drive fetch_all with a scripted sequence of fetch results; count the attempts."""
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    cfg = tmp_path / "customer_sheets.json"
    cfg.write_text('{"service_account_key": "%s"}' % str(key).replace("\\", "/"),
                   encoding="utf-8")
    calls = []

    def fake_run(cmd, timeout=600):
        calls.append(cmd)
        return outputs[min(len(calls), len(outputs)) - 1]
    monkeypatch.setattr(wi, "run", fake_run)
    monkeypatch.setattr(wi.time, "sleep", lambda s: None)
    ok, notes = wi.fetch_all(cfg, tmp_path)
    return ok, notes, len(calls)


def test_the_reason_is_the_failure_not_the_alert_path():
    out = "utility: FAILED - 403 from the export endpoint. Share it." + ALERT
    assert wi.failure_reasons(out) == ["utility: FAILED - 403 from the export endpoint. Share it."]


def test_a_failure_before_any_client_is_still_named():
    assert wi.failure_reasons("Service account key not found: C:/k.json") == \
        ["Service account key not found: C:/k.json"]


def test_a_missing_library_is_not_retried(monkeypatch, tmp_path):
    """Exactly what Saturday 2026-09-19 would have hit: key present, google-auth absent."""
    out = (1, "utility: FAILED - No module named 'google'\n"
              "arnica: FAILED - No module named 'google'" + ALERT)
    ok, notes, attempts = _fetch_all(monkeypatch, tmp_path, [out])
    assert not ok and attempts == 1
    assert any("uv sync" in n for n in notes)
    assert not any("alert written" in n for n in notes)


def test_an_unshared_sheet_is_not_retried(monkeypatch, tmp_path):
    out = (1, "arnica: FAILED - 403 from the export endpoint. The service account exists" + ALERT)
    ok, notes, attempts = _fetch_all(monkeypatch, tmp_path, [out])
    assert attempts == 1 and any("shared with the service account" in n for n in notes)


def test_a_timeout_is_still_retried_and_can_recover(monkeypatch, tmp_path):
    """The inversion. A flaky network is what the retries exist for."""
    flaky = (1, "utility: FAILED - HTTPSConnectionPool: Read timed out." + ALERT)
    ok, notes, attempts = _fetch_all(monkeypatch, tmp_path, [flaky, (0, "fetched")])
    assert ok and attempts == 2
    assert any("succeeded on attempt 2" in n for n in notes)


def test_an_unrecognised_failure_gets_every_retry(monkeypatch, tmp_path):
    odd = (1, "utility: FAILED - something nobody has seen before" + ALERT)
    ok, _, attempts = _fetch_all(monkeypatch, tmp_path, [odd])
    assert not ok and attempts == 1 + len(wi.RETRY_DELAYS)


def test_one_permanent_and_one_transient_failure_is_still_retried(monkeypatch, tmp_path):
    """All, not any: the timed-out client deserves its retry even if the other is unshared."""
    mixed = (1, "utility: FAILED - 403 from the export endpoint.\n"
                "arnica: FAILED - Read timed out." + ALERT)
    _, _, attempts = _fetch_all(monkeypatch, tmp_path, [mixed])
    assert attempts == 1 + len(wi.RETRY_DELAYS)


# ------------------------------------------------------------------------------------------------
# 2026-09-16: intake now links their rows to ours after loading. Nothing ran the matcher before, so
# every row a customer added or renamed stayed linked to nothing and research never saw it.

APPLY_OUT = """arnica  -  125 row(s) from the matcher
  certain (100%)        36  -> event_id applied
  needs review (40-99)  19  -> left unmatched, for a person

  applied      4
  already linked, left as they were  39
  needs review 13
  no match     69
  CONFLICTS    1 - the existing link was KEPT; a person decides
      Horizons Asia: linked to 2027-x (human review); the matcher is now certain of 2026-y
"""


def test_matching_reports_what_it_applied_and_what_waits_for_a_person(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, timeout=600):
        calls.append(str(cmd[1]))
        return (0, APPLY_OUT) if "apply_client_match" in str(cmd[1]) else (0, "ok")
    monkeypatch.setattr(wi, "run", fake_run)
    monkeypatch.setattr(wi, "MARKETS", tmp_path)
    monkeypatch.setattr(wi, "RUNS_OUT", tmp_path)
    (tmp_path / "Cybersecurity_audited.final.csv").write_text("EVENT_ID\n", encoding="utf-8")
    notes = wi.match_client("arnica", wi.CLIENTS["arnica"], tmp_path / "s.csv", "db")
    assert [Path(c).name for c in calls] == ["match_customer_sheet.py", "apply_client_match.py"]
    assert notes[0] == ("arnica: matching - 4 new link(s), 39 already linked, "
                        "13 for review, 69 not found")
    assert "Horizons Asia" in notes[1] and "CONFLICTS" in notes[1]


def test_matching_is_skipped_not_crashed_without_a_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(wi, "MARKETS", tmp_path)
    monkeypatch.setattr(wi, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    notes = wi.match_client("utility", wi.CLIENTS["utility"], tmp_path / "s.csv", "db")
    assert "matching skipped" in notes[0]


def test_a_failed_match_is_a_note_never_an_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(wi, "MARKETS", tmp_path)
    monkeypatch.setattr(wi, "RUNS_OUT", tmp_path)
    (tmp_path / "Utility_audited.final.csv").write_text("EVENT_ID\n", encoding="utf-8")
    monkeypatch.setattr(wi, "run", lambda cmd, timeout=600: (1, "sheet has no 'CONFERENCE' column"))
    notes = wi.match_client("utility", wi.CLIENTS["utility"], tmp_path / "s.csv", "db")
    assert notes == ["utility: matching failed - sheet has no 'CONFERENCE' column"]
