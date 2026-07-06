@echo off
REM One-click launcher for the CFP Monitor. Double-click this (or the desktop icon).
REM Does EVERYTHING: makes sure the real-Chrome (CDP) helper for hard anti-bot sites is
REM running, then opens the UI at http://localhost:8501. Sign into the Chrome window once
REM (it stays signed in). Close this window to stop.
cd /d "%~dp0.."
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM --- Ensure the CDP Chrome (real browser for hard sites) is running ---
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue)) { $c='C:\Program Files\Google\Chrome\Application\chrome.exe'; if(-not(Test-Path $c)){$c='C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'}; if(Test-Path $c){ Start-Process $c -ArgumentList '--remote-debugging-port=9222','--remote-allow-origins=*',('--user-data-dir='+$env:USERPROFILE+'\cfp-cdp-profile'),'--no-first-run','--no-default-browser-check','about:blank' } }"

REM UI auto-uses CDP for hard-block domains (Reuters); normal sites use the built-in browser.
set "CFP_CDP_URL=http://localhost:9222"

echo Starting CFP Monitor at http://localhost:8501
echo (A Chrome window may open for hard sites - sign in once; it stays signed in.)
uv run streamlit run app.py
echo.
echo CFP Monitor stopped. Press any key to close.
pause >nul
