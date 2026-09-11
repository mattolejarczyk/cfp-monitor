"""Fetch a customer's master sheet as CSV, with no human and no browser.

WHY THIS EXISTS (closes N5)
Taking the weekly copy was the last manual step in the loop: open the sheet in a signed-in
browser, hit the export URL, save the file, then run snapshot_customer_sheet.py against it.
Five minutes a week, and a process that depends on remembering is not a process - it is a
step that gets skipped on the week everything else is on fire.

WHAT IT DOES NOT DO
It does not replace snapshot_customer_sheet.py. That script owns hashing, refusing to
overwrite, and validating that a file really is the customer's sheet. This one only obtains
the bytes and hands them over, so there is exactly one path into the snapshot store.

    python scripts/fetch_customer_sheet.py --client client-a
    python scripts/fetch_customer_sheet.py --client all --alert

AUTHENTICATION: a read-only service account, not a logged-in browser
A browser session expires, wedges, and needs a human to log back in - the failure mode that
already costs us the Skool sync. A service account holds no user session, so an unattended
2am run either works or fails loudly for a reason a human can act on.

ONE-TIME SETUP, done by the operator (not by this script - it cannot create credentials):
  1. In Google Cloud, create a project, enable the Google Drive API, create a SERVICE
     ACCOUNT, and download its JSON key.
  2. Share BOTH customer sheets with that service account's email address, VIEWER access.
     Viewer is enough and is the whole point: this can never edit the customer's sheet.
  3. Save the key somewhere outside this repo (this repo is PUBLIC) and point the config at
     it - see CONFIG below.

CONFIG lives outside this repo, because the sheet IDs are customer detail and this repo is
public. Default location:  %LOCALAPPDATA%\\CFP-Monitor\\customer_sheets.json

    {
      "service_account_key": "C:/path/to/key.json",
      "clients": {
        "client-a": { "sheet_id": "...", "gid": "..." },
        "client-b": { "sheet_id": "...", "gid": "..." }
      }
    }

WHY /export?format=csv AND NEVER /gviz/tq
gviz types each column and silently drops whatever does not conform. It blanked eight real
sponsorship figures and five free-text dates once already, and the diff reported them as
customer edits. The export endpoint returns the sheet as the customer sees it.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REQUIRED = ("CONFERENCE", "SUBMISSION DEADLINE", "STATUS")
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_CONFIG = Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor" / "customer_sheets.json"
HERE = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"No config at {path}.\n"
            "Create it with the service account key path and each client's sheet_id/gid - "
            "see the CONFIG section at the top of this file."
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fetch_csv(sheet_id: str, gid: str, key_path: Path, timeout: int = 60) -> str:
    """The sheet as CSV text, via a read-only service account token."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    import requests

    creds = service_account.Credentials.from_service_account_file(str(key_path), scopes=SCOPES)
    creds.refresh(Request())
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"}, timeout=timeout)

    if r.status_code == 404:
        raise RuntimeError(
            "404 from the export endpoint. Either the sheet_id is wrong, or the sheet has not "
            "been shared with the service account - a sheet it cannot see is indistinguishable "
            "from one that does not exist."
        )
    if r.status_code in (401, 403):
        raise RuntimeError(
            f"{r.status_code} from the export endpoint. The service account exists but is not "
            "allowed to read this sheet. Share the sheet with its email address as Viewer."
        )
    r.raise_for_status()
    # A sign-in redirect returns 200 with an HTML page. Caught here rather than stored as a
    # snapshot and diffed next week as though the customer had emptied their list.
    if r.text.lstrip().lower().startswith(("<!doctype html", "<html")):
        raise RuntimeError(
            "The export returned an HTML page, not CSV - that is a sign-in or permission "
            "redirect. Nothing was saved."
        )
    return r.text


def validate(text: str, client: str) -> int:
    # Headers come from the reader, NOT from the first row: an export with a header line and
    # no data would otherwise report "missing columns" and send the reader to check the gid,
    # when the real news is that the sheet came back empty.
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    rows = list(reader)
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise RuntimeError(
            f"{client}: the export is missing column(s) {missing}. Wrong tab (check the gid) "
            "or the sheet's shape has changed. Nothing was saved."
        )
    if not rows:
        raise RuntimeError(f"{client}: the export parsed as CSV but has no rows. Nothing was saved.")
    return len(rows)


def raise_alert(lines: list[str]) -> None:
    """Same pattern as the other unattended jobs: leave a file where it cannot be missed."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = "\n".join([f"NEEDS ATTENTION - customer sheet fetch ({stamp})", ""] + lines + [
        "",
        "Re-run by hand:",
        "  python scripts/fetch_customer_sheet.py --client all",
        "",
        "This file is deleted automatically on the next successful fetch.",
    ])
    for target in alert_paths():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        except Exception:
            pass


def alert_paths() -> list[Path]:
    home = Path.home()
    return [
        home / "Documents" / "obsidian" / "Agentic OS" / "NEEDS ATTENTION - Customer Sheet Fetch.md",
        home / "Desktop" / "CUSTOMER-SHEET-FETCH-FAILED.txt",
    ]


def clear_alert() -> None:
    for target in alert_paths():
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass


def snapshot(csv_text: str, client: str, out_dir: str | None) -> int:
    """Hand the bytes to snapshot_customer_sheet.py, which owns the snapshot store."""
    tmp = Path(tempfile.gettempdir()) / f"cfp_fetch_{client}_{os.getpid()}.csv"
    tmp.write_text(csv_text, encoding="utf-8", newline="")
    try:
        cmd = [sys.executable, str(HERE / "snapshot_customer_sheet.py"),
               "--csv", str(tmp), "--client", client]
        if out_dir:
            cmd += ["--out-dir", out_dir]
        return subprocess.run(cmd, check=False).returncode
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch a customer master sheet as CSV and snapshot it.")
    ap.add_argument("--client", required=True, help="client key from the config, or 'all'")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--out-dir", default=os.environ.get("CFP_CUSTOMER_SNAPSHOTS"))
    ap.add_argument("--alert", action="store_true",
                    help="write an alert file on failure (for unattended runs)")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="fetch and validate only, do not store a snapshot")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    key_path = Path(cfg["service_account_key"])
    if not key_path.exists():
        raise SystemExit(f"Service account key not found: {key_path}")

    clients = list(cfg["clients"]) if args.client == "all" else [args.client]
    unknown = [c for c in clients if c not in cfg["clients"]]
    if unknown:
        raise SystemExit(f"Unknown client(s) {unknown}. Config has: {list(cfg['clients'])}")

    problems: list[str] = []
    for client in clients:
        entry = cfg["clients"][client]
        try:
            text = fetch_csv(entry["sheet_id"], str(entry["gid"]), key_path)
            rows = validate(text, client)
            print(f"{client}: fetched {rows} rows ({len(text):,} bytes)")
            if not args.no_snapshot:
                code = snapshot(text, client, args.out_dir)
                if code != 0:
                    problems.append(f"{client}: snapshot step exited {code}")
        except Exception as exc:
            print(f"{client}: FAILED - {exc}", file=sys.stderr)
            problems.append(f"{client}: {exc}")

    if problems:
        if args.alert:
            raise_alert(problems)
            print(f"\nalert written: {alert_paths()[1]}", file=sys.stderr)
        return 1
    if args.alert:
        clear_alert()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
