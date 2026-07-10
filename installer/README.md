# Customer installer (Windows)

One script sets up everything on a customer's PC — Python, the app, the crawler browser, their
license, and a Desktop shortcut. **No provider key ever touches their machine**; all LLM calls go
through your licensed proxy.

## Vendor: prepare a customer
1. Issue their key on the VPS: `... admin issue --customer "Name" --plan pro --quota 20000000`.
2. Send them **two things**: the file `installer/install.ps1` and their key (`cfp_…`).

## Customer: install (once)
Right-click `install.ps1` → **Run with PowerShell**, and paste the key when asked — or run:
```
powershell -ExecutionPolicy Bypass -File install.ps1 -LicenseKey cfp_theirkey
```
It downloads the app, installs dependencies + the crawler browser (a few minutes, one Chromium
download), writes their config, and adds a **CFP Monitor** Desktop icon. They double-click it to
start; a browser tab opens the app. Revoke their key and the app shows "License inactive" and
won't crawl.

## What it configures
`%LOCALAPPDATA%\CFP-Monitor\.env`:
```
CFP_LLM_PROXY_URL=https://channeled.org/cfp-proxy
CFP_LICENSE_KEY=cfp_theirkey
CFP_CDP_URL=http://localhost:9222
```

## Validate before distributing
Fast, isolated check of the installer logic (no heavy downloads, own folder, no desktop clutter):
```
install.ps1 -LicenseKey cfp_test -SkipDeps -InstallDir C:\Temp\cfp -ShortcutDir C:\Temp\cfp
```
Verified 2026-07-09: app files, venv, `.env`, launcher `.bat`, and shortcut all produced correctly;
Python pinned to 3.11/3.12 (winget-installs 3.12 if absent). The **full** run (with deps) still
wants **one smoke test on a real/clean Windows profile** — see below.

## Notes / status
- **Hardened for clean-machine unknowns:** if `winget` is absent the script prints a clear
  python.org install path (and re-verifies Python landed after a winget install); the launcher prints
  a friendly note when Google Chrome isn't installed (normal sites still crawl - only hard anti-bot
  needs Chrome). The script is ASCII-only so the PowerShell 5.1 parser can't trip on stray Unicode.
- Full end-to-end (deps + first launch showing the license banner) should still be smoke-tested once
  on a clean machine: `install.ps1 -LicenseKey <valid-key>`, then double-click the Desktop icon and
  confirm the app opens with a green "License active" banner.
- Requires internet during install (downloads app + deps + Chromium) and Google Chrome for hard
  anti-bot sites.
- **v2 polish:** wrap `install.ps1` in an Inno Setup `.exe` for a signed double-click installer +
  auto-update. The script above is the engine that installer would call.
