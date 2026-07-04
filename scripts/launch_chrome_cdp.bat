@echo off
REM Launch Chrome with a CDP remote-debugging port so cfp-monitor can drive a REAL
REM browser (beats IP-reputation anti-bot like Reuters Events). A dedicated profile
REM keeps your normal Chrome untouched. Keep this window open while crawling; close
REM it (or close Chrome) to stop. Then run crawls with CFP_CDP_URL=http://localhost:9222
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set "PROFILE=%USERPROFILE%\cfp-cdp-profile"
echo Launching Chrome with CDP on http://localhost:9222
echo Profile: %PROFILE%
"%CHROME%" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check about:blank
