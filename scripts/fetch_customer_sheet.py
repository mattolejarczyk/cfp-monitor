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

# THE SHAPE RULES BELONG TO THE WORKSTREAM, NOT TO THE FETCHER.
# Added 2026-09-20, when the awards sheets were wired up. REQUIRED above was written when
# conferences were the only customer sheet, and it is correct for them. The awards sheets
# are a different shape and would have failed it three ways: they key on AWARD rather than
# CONFERENCE, and the two customers do not agree on the status column - Arnica's awards
# sheet says STATUS, Utility Global's says SUBMISSION STATUS.
#
# That last one is why ONE_OF exists rather than a longer REQUIRED list. The disagreement
# is a NAME difference, not a value difference (see build_awards_seed.py, which documents
# the same split), so demanding both columns would reject a healthy sheet, and demanding
# neither would let a sheet with no customer signal through unnoticed. "At least one of"
# is what we actually mean.
#
# A client entry with no "kind" is a conference sheet, so a config written before this
# change keeps working unaltered.
REQUIRED_BY_KIND = {
    "conference": ("CONFERENCE", "SUBMISSION DEADLINE", "STATUS"),
    "awards":     ("AWARD", "SUBMISSION DEADLINE"),
}
ONE_OF_BY_KIND = {
    "conference": (),
    "awards":     ("STATUS", "SUBMISSION STATUS"),
}
DEFAULT_KIND = "conference"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_CONFIG = Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor" / "customer_sheets.json"
HERE = Path(__file__).resolve().parent
# Where a refused export is KEPT (quality by design rule 2: every failure keeps its evidence). Until 2026-11-07
# a refused export was thrown away ("Nothing was saved"), so when the Utility Global sheet came back with cell
# A1 blank the cause could only be found by fetching again. Same root as the other QA reports
# (src/cfp_monitor/qa_report.QA_ROOT), one folder per day: runs_out/qa/<date>/intake_failed_<client>.csv
QA_ROOT = Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor" / "runs_out" / "qa"


def keep_evidence(text: str, client: str, evidence_dir: Path | None = None) -> Path:
    """Write the raw export where a person can read it, and return the path (named in the error)."""
    d = Path(evidence_dir) if evidence_dir else QA_ROOT / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"intake_failed_{client}.csv"
    out.write_text(text, encoding="utf-8", newline="")
    return out


def _split_header(text: str) -> tuple[str, list[str], str, str]:
    """(bom, header cells, line ending, rest). The header line is parsed as CSV; the data rows are untouched."""
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom):]
    first, nl, rest = body.partition("\n")
    eol = "\r\n" if first.endswith("\r") else "\n"
    cells = next(csv.reader(io.StringIO(first.rstrip("\r"))), [])
    return bom, cells, eol if nl else "", rest


def map_blank_first_header(text: str, kind: str) -> tuple[str, str | None]:
    """The 2026-11-07 Utility Global case: cell A1 blank (spaces), every other required column present, 84 rows
    intact. When the ONLY missing required column is CONFERENCE and the first header cell is blank or whitespace,
    the first column IS the conference column by position: name it, and say so. Anything else is left for
    validate() to refuse. Conference sheets only (the case seen); an awards sheet keys on AWARD and is refused."""
    if kind != "conference":
        return text, None
    bom, cells, eol, rest = _split_header(text)
    if not cells or cells[0].strip() or not eol:
        return text, None
    required = REQUIRED_BY_KIND[kind]
    present = [c.strip() for c in cells]
    missing = [c for c in required if c not in present]
    if missing != ["CONFERENCE"]:
        return text, None
    cells[0] = "CONFERENCE"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(cells)
    return bom + buf.getvalue() + eol + rest, (
        "header cell A1 was blank; every other required column was present, so the first column was "
        "mapped to CONFERENCE by position (the customer's sheet has lost its A1 header - ask for it back)")


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


def validate(text: str, client: str, kind: str = DEFAULT_KIND,
             evidence_dir: Path | None = None) -> tuple[int, str, str | None]:
    """(row count, the text to snapshot, a note when the header was mapped). Raises RuntimeError on refusal,
    and EVERY refusal first keeps the raw export under runs_out/qa/<date>/ and names that file."""
    # Headers come from the reader, NOT from the first row: an export with a header line and
    # no data would otherwise report "missing columns" and send the reader to check the gid,
    # when the real news is that the sheet came back empty.
    required = REQUIRED_BY_KIND.get(kind)
    if required is None:
        # An unknown kind must not silently fall back to the conference shape and "pass".
        kept = keep_evidence(text, client, evidence_dir)
        raise RuntimeError(
            f"{client}: unknown sheet kind {kind!r}. Known kinds: "
            f"{sorted(REQUIRED_BY_KIND)}. The export is kept at {kept}."
        )
    text, note = map_blank_first_header(text, kind)
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    rows = list(reader)

    missing = [c for c in required if c not in headers]
    if missing:
        kept = keep_evidence(text, client, evidence_dir)
        if headers and not (headers[0] or "").strip():
            # The 2026-11-07 shape, but with more than the first column wrong: not a wrong tab.
            hint = (f"The first header cell (A1) is blank - header cell blank, not a wrong tab: the sheet's "
                    f"header row has been edited (missing {missing}).")
        else:
            hint = "Wrong tab (check the gid) or the sheet's shape has changed."
        raise RuntimeError(
            f"{client}: the {kind} export is missing column(s) {missing}. {hint} "
            f"The export is kept at {kept}."
        )

    one_of = ONE_OF_BY_KIND.get(kind, ())
    if one_of and not any(c in headers for c in one_of):
        kept = keep_evidence(text, client, evidence_dir)
        raise RuntimeError(
            f"{client}: the {kind} export carries none of {list(one_of)}. One of them holds "
            f"the customer's own status, which is the signal we read and never write. "
            f"The export is kept at {kept}."
        )

    if not rows:
        kept = keep_evidence(text, client, evidence_dir)
        raise RuntimeError(f"{client}: the export parsed as CSV but has no rows. The export is kept at {kept}.")
    return len(rows), text, note


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


def snapshot(csv_text: str, client: str, out_dir: str | None,
             kind: str = DEFAULT_KIND) -> int:
    """Hand the bytes to snapshot_customer_sheet.py, which owns the snapshot store.

    The kind goes with them. That script checks the shape AGAIN, independently, and it is
    right to - it is the last thing between a sign-in redirect and the store, and it is not
    supposed to trust this caller. Passing the kind tells it which shape to demand; it does
    not tell it to skip the demand.
    """
    tmp = Path(tempfile.gettempdir()) / f"cfp_fetch_{client}_{os.getpid()}.csv"
    tmp.write_text(csv_text, encoding="utf-8", newline="")
    try:
        cmd = [sys.executable, str(HERE / "snapshot_customer_sheet.py"),
               "--csv", str(tmp), "--client", client, "--kind", kind]
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
            kind = entry.get("kind", DEFAULT_KIND)
            text = fetch_csv(entry["sheet_id"], str(entry["gid"]), key_path)
            rows, text, note = validate(text, client, kind)
            print(f"{client}: fetched {rows} rows ({len(text):,} bytes) [{kind}]")
            if note:
                print(f"{client}: NOTE - {note}")
            if not args.no_snapshot:
                code = snapshot(text, client, args.out_dir, kind)
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
