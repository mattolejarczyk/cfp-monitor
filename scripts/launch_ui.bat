@echo off
REM One-click launcher for the CFP Monitor UI. Double-click this file.
REM Opens a browser at http://localhost:8501 with the Run & Crawl + Review & Verify tabs.
cd /d "%~dp0.."
echo Starting CFP Monitor UI at http://localhost:8501  (close this window to stop)
uv run streamlit run app.py
