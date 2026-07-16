# Windows licensed desktop installation and recovery

This is the canonical support runbook for the customer-facing CFP Monitor desktop app.
It records the required paths, configuration, launcher behavior, and the validation sequence.
Never put a license key, LLM key, or proxy credential in this document, a ticket, or a screenshot.
Use `[REDACTED]` in examples.

## 1. Two installations must not be confused

| Installation | Purpose | Customer-list status |
|---|---|---|
| `C:\Users\matts\cfp-monitor` | Historical developer build; may contain a direct provider configuration. | Keep only as a recovery/reference copy. Do not use for customer lists until any old direct-provider key has been rotated. |
| `%LOCALAPPDATA%\CFP-Monitor` | Licensed customer build. Routes extraction through the managed proxy. | The only approved build for customer work. |

Do not copy `.env` from the developer build into the licensed build.

## 2. Required licensed installation layout

The installer creates and maintains the following files:

```text
%LOCALAPPDATA%\CFP-Monitor\
  CFP-Monitor.bat
  .env
  app.py
  venv\Scripts\python.exe
```

The required configuration file is `%LOCALAPPDATA%\CFP-Monitor\.env` and contains only the managed-proxy configuration:

```text
CFP_LLM_PROXY_URL=https://channeled.org/cfp-proxy
CFP_LICENSE_KEY=[REDACTED]
CFP_CDP_URL=http://localhost:9222
```

There must be no customer-side provider key such as `OPENROUTER_API_KEY` in this licensed `.env`.
The installer writes this file without a UTF-8 BOM because a BOM can corrupt the first variable for
some Windows readers.

## 3. Desktop shortcut contract

The installer creates this shortcut:

```text
%USERPROFILE%\Desktop\CFP Monitor.lnk
```

Its required properties are:

```text
Target:            %LOCALAPPDATA%\CFP-Monitor\CFP-Monitor.bat
Start in:          %LOCALAPPDATA%\CFP-Monitor
```

The shortcut must never target the historical developer launcher
`C:\Users\matts\cfp-monitor\scripts\launch_ui.bat` for customer work.

Double-clicking the approved shortcut starts the licensed launcher, opens Streamlit, and should show
a `License active` banner. This banner is the practical confirmation that the managed proxy and
license configuration were loaded.

## 4. What the launcher does

`CFP-Monitor.bat` is intentionally the single launch entry point. It:

1. Starts a dedicated Google Chrome profile with remote debugging on port `9222` if that port is not
   already listening.
2. Uses `%USERPROFILE%\cfp-cdp-profile` for that dedicated Chrome session, keeping it separate from
   the user's normal Chrome profile.
3. Starts Streamlit with the licensed virtual environment:
   `venv\Scripts\python.exe -m streamlit run app.py`.
4. Keeps the launcher window open while the app runs.

Chrome login is not required for ordinary sites. Leave the dedicated Chrome window open during a run;
it provides the real-browser/CDP fallback for JS-heavy or hard anti-bot sites. Chrome is optional for
ordinary crawling but needed for that fallback.

## 5. Install and update procedure

Use the current `installer/install.ps1` from the repository. It downloads the current `main` branch,
creates or refreshes the virtual environment, installs dependencies and crawler browser support,
writes the licensed `.env`, and recreates the Desktop shortcut.

For an update, close CFP Monitor and rerun the installer with the existing `cfp_...` license key.
This is the supported recovery/update route because it refreshes the app files, dependency set,
configuration, launcher, and shortcut together. Do not manually mix files from the developer and
licensed folders.

The installer stops when a native dependency install fails. The supported LiteLLM constraint is
pinned in `pyproject.toml` to avoid a Windows source build that would otherwise require Rust/Cargo.
A successful repair should be verified by confirming that the licensed virtual environment can run:

```text
python.exe -m streamlit --version
```

before launching the app.

## 6. Post-install verification checklist

Complete these checks in order:

1. `%LOCALAPPDATA%\CFP-Monitor\CFP-Monitor.bat`, `.env`, and
   `venv\Scripts\python.exe` exist.
2. Launch using the Desktop shortcut, not the developer folder.
3. Confirm `License active` is visible at `http://localhost:8501`.
4. Confirm port `9222` is listening if Chrome/CDP fallback is needed.
5. Run one known-good conference URL. Confirm a result is stored and the output is reasonable.
6. Before processing a customer list, normalize/deduplicate the URLs and confirm the resulting list
   is correct.

## 7. Customer-list intake guardrails

- `.txt` and `.csv` inputs extract HTTP(S) URLs from text.
- Customer `.xlsx` files use literal URL values in visible **Column B** as crawl targets. The same row's
  **A/C/D** values (name, location, event date) are retained only for one-hop directory/organization-page
  resolution. Excel package XML, hyperlink metadata, notes, and all other columns are not crawl targets.
- The UI reports the normalized/deduplicated URL count before a run. Stop and correct the input if it
  does not match the expected list.
- A bad or stale source URL is an input-quality failure, not evidence that the crawler failed.
  Never silently replace a supplied URL; correct it in the source list and rerun it.
- Process customer lists sequentially so each result set remains auditable.

## 8. Customer output compatibility

The customer table and CSV are normalized to Excel-safe ASCII at the final presentation layer.
The extraction prompt also asks for ordinary ASCII punctuation. Together these prevent em/en dashes,
curly punctuation, and mojibake such as `â€”` in customer fields. Source evidence remains available
for auditability; the compatibility normalization applies to the customer-facing output.

## 9. Fast recovery decision tree

| Symptom | Recovery path |
|---|---|
| Shortcut opens the old developer app or no active-license banner | Rerun the current installer, then launch the recreated Desktop shortcut. Do not copy the developer `.env`. |
| `No module named streamlit` | The licensed venv is incomplete. Rerun the current installer so dependencies are installed and checked together. |
| LiteLLM metadata/Rust/Cargo error | Use the current installer and current `pyproject.toml`; do not install Rust as a customer workaround. |
| Normal sites work but a hard anti-bot site does not | Confirm Chrome is installed, the dedicated Chrome window remains open, and port `9222` is listening. |
| Unexpected XLSX URLs | Confirm the intended literal URLs are in Column B and that the displayed unique count matches the expected list before clicking Run. |
| Garbled punctuation in an old saved export | Rerun the affected URL after updating, then use the current customer-format output. |
