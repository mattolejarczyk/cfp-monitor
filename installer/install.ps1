<#
  CFP Monitor  -  one-shot customer installer (Windows).

  What it does (no Python/terminal knowledge needed by the customer):
    1. Finds Python 3.11/3.12 (installs 3.12 via winget if missing  -  the version the app is pinned to).
    2. Downloads the app from the public repo (no git needed).
    3. Creates an isolated venv and installs all dependencies.
    4. Installs the Playwright Chromium the crawler uses.
    5. Writes the customer's .env  (proxy URL baked in + their license key).
    6. Creates a Desktop shortcut "CFP Monitor" that launches the app.

  VENDOR usage  -  give the customer their key, then they run (right-click > Run with PowerShell):
     powershell -ExecutionPolicy Bypass -File install.ps1 -LicenseKey cfp_theirkey

  Validation (fast, no heavy downloads, isolated):
     install.ps1 -LicenseKey cfp_test -SkipDeps -InstallDir C:\Temp\cfp -ShortcutDir C:\Temp\cfp
#>
param(
  [Parameter(Mandatory = $true)][string]$LicenseKey,
  [string]$ProxyUrl = "https://channeled.org/cfp-proxy",
  [string]$InstallDir = "$env:LOCALAPPDATA\CFP-Monitor",
  [string]$ShortcutDir = [Environment]::GetFolderPath('Desktop'),
  [switch]$SkipDeps
)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }

# 1. Python 3.11/3.12 -------------------------------------------------------
Say "Checking for Python 3.11/3.12"
$py = $null; $anypy = $null
foreach ($c in @("py -3.12", "py -3.11", "python", "py")) {
  try { $e, $a = $c.Split(" "); $v = & $e $a --version 2>$null } catch { continue }
  if (-not $v) { continue }
  if (-not $anypy) { $anypy = $c }
  if ($v -match "3\.(11|12)\b") { $py = $c; break }
}
if (-not $py -and $SkipDeps -and $anypy) {
  Write-Host "   (validation) no 3.11/3.12; using '$anypy' just to build the venv" -ForegroundColor Yellow
  $py = $anypy
}
elseif (-not $py) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Python 3.11 or 3.12 is required but wasn't found, and 'winget' (the Windows app" -ForegroundColor Red
    Write-Host "installer) isn't available on this PC  -  so I can't install Python automatically." -ForegroundColor Red
    Write-Host "Please install Python 3.12 yourself, then run this installer again:" -ForegroundColor Yellow
    Write-Host "  1. Open https://www.python.org/downloads/  and download Python 3.12" -ForegroundColor Yellow
    Write-Host "  2. In the installer, TICK 'Add python.exe to PATH', then Install" -ForegroundColor Yellow
    Write-Host "  3. Re-run this CFP Monitor installer" -ForegroundColor Yellow
    exit 1
  }
  Say "Installing Python 3.12 via winget"
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  # Verify it actually landed (winget can no-op or fail without throwing).
  $py = $null
  foreach ($c in @("py -3.12", "py -3.11")) {
    try { $e, $a = $c.Split(" "); if ((& $e $a --version 2>$null) -match "3\.(11|12)\b") { $py = $c; break } } catch {}
  }
  if (-not $py) {
    Write-Host ""
    Write-Host "The automatic Python 3.12 install didn't complete. Please install it manually and" -ForegroundColor Red
    Write-Host "re-run: https://www.python.org/downloads/  (tick 'Add python.exe to PATH')." -ForegroundColor Yellow
    exit 1
  }
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
Say "Creating environment"
Push-Location $InstallDir
$e, $a = $py.Split(" ")
if ($a) { & $e $a -m venv venv } else { & $e -m venv venv }
$vpy = "$InstallDir\venv\Scripts\python.exe"
if (-not $SkipDeps) {
  Say "Installing dependencies (a few minutes)"
  & $vpy -m pip install --quiet --upgrade pip
  & $vpy -m pip install --quiet .
  Say "Installing the crawler browser (Chromium download)"
  & $vpy -m playwright install chromium
  try { & "$InstallDir\venv\Scripts\crawl4ai-setup.exe" } catch { }
} else {
  Write-Host "   (validation) skipping pip install / Playwright" -ForegroundColor Yellow
}

# 5. Customer .env (proxy + their license; no LLM key on their machine) -----
# Write WITHOUT a BOM  -  PowerShell's Set-Content -Encoding UTF8 adds one, which corrupts the
# first line so CFP_LLM_PROXY_URL wouldn't be read.
Say "Writing configuration"
$envText = "CFP_LLM_PROXY_URL=$ProxyUrl`r`nCFP_LICENSE_KEY=$LicenseKey`r`nCFP_CDP_URL=http://localhost:9222`r`n"
[System.IO.File]::WriteAllText("$InstallDir\.env", $envText, (New-Object System.Text.UTF8Encoding($false)))

# 6. Launcher (.bat is fully static -> literal here-string, no escaping) -----
$launcher = "$InstallDir\CFP-Monitor.bat"
@'
@echo off
cd /d "%~dp0"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue) { exit }; $c='C:\Program Files\Google\Chrome\Application\chrome.exe'; if(-not(Test-Path $c)){$c='C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'}; if(Test-Path $c){ Start-Process $c -ArgumentList '--remote-debugging-port=9222','--remote-allow-origins=*',('--user-data-dir='+$env:USERPROFILE+'\cfp-cdp-profile'),'--no-first-run','--no-default-browser-check','about:blank' } else { Write-Host 'Note: Google Chrome was not found. Normal sites will still crawl fine; only hard anti-bot sites (e.g. Reuters) need Chrome installed. Install Chrome and relaunch if you need those.' -ForegroundColor Yellow }"
"venv\Scripts\python.exe" -m streamlit run app.py
pause
'@ | Set-Content -Encoding ASCII $launcher

# Desktop shortcut
New-Item -ItemType Directory -Force -Path $ShortcutDir | Out-Null
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$ShortcutDir\CFP Monitor.lnk")
$sc.TargetPath = $launcher
$sc.WorkingDirectory = $InstallDir
$sc.IconLocation = "shell32.dll,13"
$sc.Save()
Pop-Location

# Non-fatal heads-up: Chrome is only needed for hard anti-bot sites (via CDP), not normal crawling.
$chrome = @("C:\Program Files\Google\Chrome\Application\chrome.exe",
            "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ }
if (-not $chrome) {
  Write-Host "Heads-up: Google Chrome wasn't found. The app runs fine and crawls normal sites;" -ForegroundColor Yellow
  Write-Host "install Chrome only if you need hard anti-bot sites (e.g. Reuters)." -ForegroundColor Yellow
}

Say "Done. Double-click 'CFP Monitor' on your Desktop to start."
Say "Installed to: $InstallDir"
