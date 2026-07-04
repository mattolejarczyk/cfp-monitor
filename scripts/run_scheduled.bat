@echo off
REM Run-once scheduled CFP monitor job (M6). Register in Windows Task Scheduler:
REM   Task Scheduler -> Create Basic Task -> weekly -> "Start a program" -> this .bat.
REM Edit the URL list at examples\urls.txt. Optionally set CFP_CDP_URL for hard sites and
REM the CFP_SMTP_* / CFP_ALERT_TO env vars to email the alert digest.
cd /d "%~dp0.."
uv run python -m cfp_monitor.scheduler --urls examples\urls.txt --db cfp_monitor.db --out runs_out
