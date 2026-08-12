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

REM Resolve Chrome OUTSIDE the block below. Inside one, "!CHROME!" needs delayed expansion
REM which this script does not enable, so the 32-bit fallback never took effect and the
REM start line had to hard-code the 64-bit path to work at all.
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"

venv\Scripts\python.exe scripts\cdp_ctl.py check >nul 2>&1
if errorlevel 1 (
  echo Starting CDP Chrome on 9222 >> "%LOG%"
  start "" /min "%CHROME%" ^
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

REM ---------------------------------------------------------------------------
REM Weekly DISCOVERY - the only part of this job that spends API quota.
REM Scoped to rows that are unconfirmed AND still have a future deadline: 9 today,
REM so ~9 grounded requests a week rather than the ~400 a full re-research costs.
REM That scoping is what makes it safe to run weekly; the script refuses outright
REM if more rows qualify than --max-rows, because a spike means a data problem.
REM Added 2026-08-12: the customer briefing promises new 2027 calls are caught
REM within a week, and before this the answer was a month.
REM Anything it finds still has to clear the merge guard - fetched, and the quote
REM proven on the page - so --apply here cannot land an unverified date.
REM Skipped silently if the key or upstream's script is absent; verification has
REM already run by this point and must not be lost to a discovery failure.
REM ---------------------------------------------------------------------------
REM A subroutine, not an if/else block: %ERRORLEVEL% inside a parenthesised block expands
REM when the block is PARSED, not when it runs, so the exit code logged there would be a
REM stale value. Calling out avoids that and avoids a goto out of a block.
call :discovery


if defined WE_STARTED_CHROME (
  echo Stopping the CDP Chrome we started >> "%LOG%"
  venv\Scripts\python.exe scripts\cdp_ctl.py stop >> "%LOG%" 2>&1
)

echo Finished with exit code %RC%. Log: %LOG%
exit /b %RC%


REM ---------------------------------------------------------------------------
REM :discovery
REM Never changes %RC%. Verification has already run by the time we get here and a
REM discovery failure must not be reported as a failed weekly sweep.
REM
REM The candidate list is REGENERATED from the database every week, never read from a
REM dated snapshot. A frozen file could only ever hold the 93 rows audited on 2026-08-11,
REM so a row that goes unconfirmed in October would never enter the queue - and nothing
REM would report the omission. Verified 2026-08-12: regenerating gives 94 rows and picks
REM out the same 9 open ones.
REM ---------------------------------------------------------------------------
:discovery
set "DISCOVERY=%USERPROFILE%\Desktop\Nicolia-PR-Prime\Markets\extract_candidate_urls.py"
set "AUDITED=%LOGDIR%\unconfirmed_%STAMP%.csv"

if not defined GEMINI_API_KEY (
  echo Skipping discovery - GEMINI_API_KEY not set >> "%LOG%"
  exit /b 0
)
if not exist "%DISCOVERY%" (
  echo Skipping discovery - upstream script not found at %DISCOVERY% >> "%LOG%"
  exit /b 0
)

echo Rebuilding the unconfirmed list from the database >> "%LOG%"
venv\Scripts\python.exe scripts\unconfirmed_citations.py --db cfp_monitor.db ^
  --seed-dir market_sheets --out "%AUDITED%" >> "%LOG%" 2>&1
if not exist "%AUDITED%" (
  echo Skipping discovery - could not rebuild the unconfirmed list >> "%LOG%"
  exit /b 0
)

REM REPORT-ONLY, deliberately - no --apply. Discovery runs unattended and writes the gate
REM result to the digest; a human merges it. The merge guard is strong (it re-fetches and
REM requires the quote on the page, so it cannot pass an unverified date) but it has never
REM run unattended, and nine rows a week is small enough that review costs almost nothing.
REM The customer promise is that a new call is CAUGHT within a week, and a digest on Sunday
REM applied on Monday keeps that true. Decided 2026-08-12; revisit once this has run clean
REM for a few weeks.
echo Weekly discovery starting - REPORT ONLY, merge is a human step >> "%LOG%"
venv\Scripts\python.exe scripts\weekly_discovery.py --db cfp_monitor.db ^
  --source "%AUDITED%" --out-dir "%LOGDIR%" --max-rows 25 ^
  --discovery-script "%DISCOVERY%" --run-discovery >> "%LOG%" 2>&1
echo Discovery finished with exit code %ERRORLEVEL% >> "%LOG%"
exit /b 0
