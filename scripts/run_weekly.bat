@echo off
setlocal
REM ---------------------------------------------------------------------------
REM Weekly CFP re-verification sweep. Register in Windows Task Scheduler:
REM
REM   schtasks /create /tn "CFP Weekly Verification" /tr "<live>\scripts\run_weekly.bat" ^
REM            /sc weekly /d SUN /st 01:00 /f
REM
REM Runs from the LIVE build and uses ITS interpreter - never `uv` from this
REM directory, which strands a .venv here (runbook, section 0).
REM
REM Makes no LLM calls and spends no API quota. Discovery is the separate MONTHLY
REM grounded audit in the upstream working area; this job only re-checks what is
REM already loaded.
REM
REM CDP CHROME. The fetch ladder's top rung needs a real Chrome on port 9222, and
REM without it hard anti-bot sites are SKIPPED rather than hammered (which would
REM get the residential IP flagged). On 2026-08-10 that rung alone recovered 53
REM claims, including Reuters Events, so the weekly job starts Chrome itself.
REM   - if something is already on 9222 we USE it and leave it alone; it is not
REM     ours to close, and it may be a human's session
REM   - if we start it, we stop it afterwards, so the job leaves no window behind
REM A dedicated profile (%USERPROFILE%\cfp-cdp-profile) keeps normal Chrome clear.
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
set "LOG=%LOGDIR%\weekly_%STAMP%.log"

REM ---- CDP Chrome -----------------------------------------------------------
set "WE_STARTED_CHROME="
venv\Scripts\python.exe scripts\cdp_ctl.py check >nul 2>&1
if errorlevel 1 (
  echo Starting CDP Chrome on 9222 >> "%LOG%"
  set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  if not exist "!CHROME!" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  start "" /min "%ProgramFiles%\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 --remote-allow-origins=* ^
    --user-data-dir="%USERPROFILE%\cfp-cdp-profile" ^
    --no-first-run --no-default-browser-check about:blank
  venv\Scripts\python.exe scripts\cdp_ctl.py wait >> "%LOG%" 2>&1
  if not errorlevel 1 set "WE_STARTED_CHROME=1"
) else (
  echo CDP already reachable on 9222 - using it, will not close it >> "%LOG%"
)
set "CFP_CDP_URL=http://localhost:9222"

echo Weekly verification starting %STAMP%
venv\Scripts\python.exe scripts\weekly_verify.py --db cfp_monitor.db >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

if defined WE_STARTED_CHROME (
  echo Stopping the CDP Chrome we started >> "%LOG%"
  venv\Scripts\python.exe scripts\cdp_ctl.py stop >> "%LOG%" 2>&1
)

echo Finished with exit code %RC%. Log: %LOG%
exit /b %RC%
