@echo off
REM Start the license + LLM proxy (vendor side). Reads licenseproxy\.env for keys/config.
REM First run: pip/uv install fastapi uvicorn (already in this project's deps).
cd /d "%~dp0.."
where uv >nul 2>nul || set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM Load licenseproxy\.env into the environment (KEY=VALUE lines) if present.
if exist "licenseproxy\.env" (
  for /f "usebackq tokens=1* delims==" %%A in ("licenseproxy\.env") do (
    echo %%A| findstr /b /c:"#" >nul || if not "%%A"=="" set "%%A=%%B"
  )
)

set "PORT=%1"
if "%PORT%"=="" set "PORT=8800"
echo Starting license proxy on http://localhost:%PORT%  (model: %PROXY_MODEL%)
uv run uvicorn licenseproxy.server:app --host 0.0.0.0 --port %PORT%
