"""Shared test guards: no test may ever send a real email (2026-11-09), read the real Task Scheduler, or wait for the customer sheets (2026-11-10).

scripts/customer_sheet_load.py sends a CRITICAL email through alerts.maybe_send_email, which reads CFP_SMTP_* and CFP_RECAP_TO from the
environment, and this PC has them set at user level. A test that forgot to stub the mailer would email Matt. With the variables removed for
every test, maybe_send_email returns False ('not configured') instead of sending."""
import pytest

MAIL_VARS = ("CFP_SMTP_HOST", "CFP_SMTP_PORT", "CFP_SMTP_USER", "CFP_SMTP_PASS", "CFP_SMTP_FROM", "CFP_RECAP_TO", "CFP_ALERT_TO")


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    for name in MAIL_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_sheet_wait(monkeypatch, tmp_path):
    """customer_sheet_load waits up to 2 hours for the sheets (Matt, 2026-11-10) and reads the research task's time limit from Task
    Scheduler. A test that did not ask for the wait gets none (CFP_SHEETS_HOLD_HOURS=0), never runs PowerShell, and writes its status file in
    tmp_path. Tests of the wait pass their own env and task reader."""
    monkeypatch.setenv("CFP_SHEETS_HOLD_HOURS", "0")
    import sys
    from pathlib import Path
    scripts = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import customer_sheet_load as csl
    except Exception:                                                         # noqa: BLE001
        return
    monkeypatch.setattr(csl, "task_info", lambda *a, **k: {})
    monkeypatch.setattr(csl, "STATUS", tmp_path / "sheet_load_status.json")
    # 2026-11-13 (D66 = B): a failed load HOLDS the research only when the live run script can enforce it (patch ACT-75 applied). The tests assume it
    # can, whatever state the live Markets script is in today; test_sheet_hold.py exercises the real check through csl._real_hold_wired.
    monkeypatch.setattr(csl, "_real_hold_wired", csl.hold_wired, raising=False)
    monkeypatch.setattr(csl, "hold_wired", lambda markets=None: True)
