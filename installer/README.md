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

## Notes / status
- **Needs one validation run on a clean Windows machine** before mass distribution (dependency
  download size, and whether the customer already has Python/Chrome). This is the last test step.
- Requires internet during install (downloads app + deps + Chromium) and Google Chrome for hard
  anti-bot sites.
- **v2 polish:** wrap `install.ps1` in an Inno Setup `.exe` for a signed double-click installer +
  auto-update. The script above is the engine that installer would call.
