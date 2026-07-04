@echo off
REM One-click launcher for the CFP Monitor UI. Double-click this (or the desktop icon).
REM Opens a browser at http://localhost:8501 with the Run & Crawl + Review & Verify tabs.
cd /d "%~dp0.."
REM Make sure uv is reachable even from a bare shortcut environment.
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
echo Starting CFP Monitor UI at http://localhost:8501
echo (Keep this window open while using it. Close it to stop.)
uv run streamlit run app.py
echo.
echo CFP Monitor stopped. Press any key to close.
pause >nul
