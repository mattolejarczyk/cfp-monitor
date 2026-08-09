@echo off
REM ---------------------------------------------------------------------------
REM Weekly CFP re-verification sweep. Register in Windows Task Scheduler:
REM
REM   schtasks /create /tn "CFP Weekly Verification" /tr "<live>\scripts\run_weekly.bat" ^
REM            /sc weekly /d MON /st 06:00 /f
REM
REM Runs from the LIVE build and uses ITS interpreter - never `uv` from this
REM directory, which strands a .venv here (runbook, section 0).
REM
REM Makes no LLM calls and spends no API quota. Discovery is the separate MONTHLY
REM grounded audit in the upstream working area; this job only re-checks what is
REM already loaded.
REM
REM Email is optional. Set these for the digest to be mailed, otherwise it is
REM written to runs_out\ only:
REM   CFP_SMTP_HOST  CFP_SMTP_PORT  CFP_SMTP_USER  CFP_SMTP_PASS  CFP_ALERT_TO
REM Set them as MACHINE-level environment variables (setx /m) so the scheduled
REM task sees them - a task running without a logged-in session does not inherit
REM the user profile's variables in every configuration.
REM ---------------------------------------------------------------------------
cd /d "%~dp0.."

if not exist "venv\Scripts\python.exe" (
  echo ERROR: no venv here. This must run from the LIVE build, not the dev repo.
  exit /b 2
)

set "LOGDIR=runs_out"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "DT=%%I"
set "STAMP=%DT:~0,8%-%DT:~8,6%"

echo Weekly verification starting %STAMP%
venv\Scripts\python.exe scripts\weekly_verify.py --db cfp_monitor.db >> "%LOGDIR%\weekly_%STAMP%.log" 2>&1
set "RC=%ERRORLEVEL%"
echo Finished with exit code %RC%. Log: %LOGDIR%\weekly_%STAMP%.log
exit /b %RC%
