<#
  CFP Monitor — one-shot customer installer (Windows).

  What it does (no Python/terminal knowledge needed by the customer):
    1. Finds Python 3.11+ (installs it via winget if missing).
    2. Downloads the app from the public repo (no git needed).
    3. Creates an isolated venv and installs all dependencies.
    4. Installs the Playwright Chromium the crawler uses.
    5. Writes the customer's .env  (proxy URL baked in + their license key).
    6. Creates a Desktop shortcut "CFP Monitor" that launches the app.

  VENDOR usage — give the customer their key, then they run (right-click > Run with PowerShell),
  or you pre-fill it:
     powershell -ExecutionPolicy Bypass -File install.ps1 -LicenseKey cfp_theirkey

  Optional: -ProxyUrl (defaults to the live proxy), -InstallDir.
#>
param(
  [Parameter(Mandatory = $true)][string]$LicenseKey,
  [string]$ProxyUrl = "https://channeled.org/cfp-proxy",
  [string]$InstallDir = "$env:LOCALAPPDATA\CFP-Monitor"
)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }

# 1. Python 3.11+ -----------------------------------------------------------
Say "Checking for Python 3.11+"
$py = $null
foreach ($c in @("py -3.12", "py -3.11", "python")) {
  try {
    $exe, $arg = $c.Split(" ")
    $v = & $exe $arg --version 2>$null
    if ($v -match "3\.(1[1-9]|[2-9]\d)") { $py = $c; break }
  } catch {}
}
if (-not $py) {
  Say "Python not found — installing via winget"
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  $py = "py -3.12"
}
Say "Using Python: $py"

# 2. Download the app -------------------------------------------------------
Say "Downloading the app"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$zip = "$env:TEMP\cfp-monitor.zip"
Invoke-WebRequest "https://github.com/mattolejarczyk/cfp-monitor/archive/refs/heads/main.zip" -OutFile $zip
$tmp = "$env:TEMP\cfp-extract"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Expand-Archive $zip -DestinationPath $tmp -Force
Copy-Item "$tmp\cfp-monitor-main\*" $InstallDir -Recurse -Force
Remove-Item $zip, $tmp -Recurse -Force

# 3-4. venv + deps + Playwright browser ------------------------------------
Say "Creating environment and installing dependencies (this takes a few minutes)"
Push-Location $InstallDir
$exe, $arg = $py.Split(" ")
& $exe $arg -m venv venv
$vpy = "$InstallDir\venv\Scripts\python.exe"
& $vpy -m pip install --quiet --upgrade pip
& $vpy -m pip install --quiet .
Say "Installing the crawler browser (Chromium download)"
& $vpy -m playwright install chromium
try { & "$InstallDir\venv\Scripts\crawl4ai-setup.exe" } catch { }

# 5. Customer .env (proxy + their license; no LLM key on their machine) -----
Say "Writing configuration"
@"
CFP_LLM_PROXY_URL=$ProxyUrl
CFP_LICENSE_KEY=$LicenseKey
CFP_CDP_URL=http://localhost:9222
"@ | Set-Content -Encoding UTF8 "$InstallDir\.env"

# 6. Launcher + Desktop shortcut -------------------------------------------
$launcher = "$InstallDir\CFP-Monitor.bat"
@"
@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "if (-not (Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue)) { `$c='C:\Program Files\Google\Chrome\Application\chrome.exe'; if(-not(Test-Path `$c)){`$c='C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'}; if(Test-Path `$c){ Start-Process `$c -ArgumentList '--remote-debugging-port=9222','--remote-allow-origins=*',('--user-data-dir='+`$env:USERPROFILE+'\cfp-cdp-profile'),'--no-first-run','--no-default-browser-check','about:blank' } }"
"venv\Scripts\python.exe" -m streamlit run app.py
pause
"@ | Set-Content -Encoding ASCII $launcher

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\CFP Monitor.lnk")
$sc.TargetPath = $launcher
$sc.WorkingDirectory = $InstallDir
$sc.IconLocation = "shell32.dll,13"
$sc.Save()
Pop-Location

Say "Done. Double-click 'CFP Monitor' on your Desktop to start."
Say "Installed to: $InstallDir"
