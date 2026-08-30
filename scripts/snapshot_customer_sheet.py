"""Take an immutable, hashed weekly copy of a customer's master sheet.

WHY THIS EXISTS (rule C7)
A real person maintains the customer's conference list by hand: they email organisers, record
what they hear in STATUS DETAILS, and mark rows "Needs Verification" for us. Until 2026-08-30
none of that reached us, and the weekly job never looked at the sheet at all.

Every question worth asking about their sheet is a question about CHANGE - what did they add,
what did they correct, what did they ask for - and none of it is answerable without last week's
copy to compare against. That is all this does. It is deliberately the dumbest step in the
process, because it has to run before anything clever can.

    python scripts/snapshot_customer_sheet.py --csv <export.csv> --client utility
    python scripts/snapshot_customer_sheet.py --csv <a.csv> --client arnica --out-dir <dir>

WHERE THE SNAPSHOTS GO
NOT into this repo, which is public. These are the customer's asset - the same rule that keeps
the golden-master delivery snapshot in the private upstream area. `--out-dir` has no baked-in
default pointing anywhere public; set CFP_CUSTOMER_SNAPSHOTS or pass it explicitly.

WHAT IT REFUSES TO DO
It never overwrites a snapshot. Two runs on the same day against a changed sheet produce two
files, because "we took a copy and it is gone" is the one failure this step cannot have. It
also refuses a file that does not parse as the customer's sheet, since a silently-truncated
export would look exactly like a customer who deleted 300 rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# The columns that make a file recognisably one of these sheets. Checked so that an HTML error
# page, a sign-in redirect, or the wrong tab of the right spreadsheet cannot be stored as a
# snapshot and then diffed next week as though the customer had emptied their list.
REQUIRED = ("CONFERENCE", "SUBMISSION DEADLINE", "STATUS")

# Their columns, by who owns them (rule C1). Recorded in the manifest rather than enforced here:
# this step only copies. But a snapshot whose shape has drifted is worth knowing about the day
# it drifts, not the week we try to diff it.
CUSTOMER_OWNED = ("STATUS", "STATUS DETAILS", "PRIORITY", "SPEAKER & ABSTRACTS SUBMITTED")
EVIDENCE = ("SUBMISSION DEADLINE", "SUBMISSION URL", "CONFERENCE URL", "LOCATION",
            "EVENT START DATE")
REQUEST = ("SUBMISSION DATE VERIFIED",)

# NEVER COPIED. Both sheets carry LOGIN and PW columns - the customer built somewhere to keep
# submission-portal credentials. They are empty today, and this snapshot runs every week into a
# git repository, so "empty today" is not a safety argument: the first week they fill one in, we
# would commit it, and git makes that permanent. The column is kept so the shape still lines up
# for a diff; the value is replaced and never written to disk.
#
# Matched case-insensitively on the stripped header, because the two sheets already disagree on
# spelling elsewhere ("NOTIFCATION DATE" in one, "NOTIFICATION DATE" in the other) and an exact
# match is one typo away from storing a password.
SECRET_COLUMNS = ("login", "pw", "password", "user", "username", "api key", "token")
REDACTED = "[REDACTED BY SNAPSHOT]"


def is_secret(header: str) -> bool:
    return header.strip().lower() in SECRET_COLUMNS


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_shape(path: Path) -> tuple[list[str], int, dict]:
    """Return (headers, data_row_count, per-class column presence).

    Uses utf-8-sig: a Google Sheets CSV export carries a BOM, and on 2026-07-09 a BOM on the
    first line of a .env cost a day of debugging because it corrupted the first key silently.
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise SystemExit(f"REFUSED: {path.name} is empty")
    headers = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any((c or "").strip() for c in r)]
    present = {
        "customer_owned": [c for c in CUSTOMER_OWNED if c in headers],
        "evidence": [c for c in EVIDENCE if c in headers],
        "request": [c for c in REQUEST if c in headers],
    }
    return headers, len(body), present


def write_redacted(src: Path, dest: Path, secret_idx: list[int]) -> int:
    """Copy the sheet to `dest` with credential columns blanked. Returns how many non-empty
    secret values were dropped - a number worth printing, because it means the customer IS
    keeping credentials there and someone should say so out loud."""
    dropped = 0
    with open(src, encoding="utf-8-sig", newline="") as fh_in, \
            open(dest, "w", encoding="utf-8", newline="") as fh_out:
        w = csv.writer(fh_out)
        for n, row in enumerate(csv.reader(fh_in)):
            if n:                                        # never touch the header row
                for i in secret_idx:
                    if i < len(row) and (row[i] or "").strip():
                        dropped += 1
                        row[i] = REDACTED
            w.writerow(row)
    return dropped


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot a customer master sheet (rule C7).")
    ap.add_argument("--csv", required=True, help="the exported CSV to snapshot")
    ap.add_argument("--client", required=True, help="short client key, e.g. utility, arnica")
    ap.add_argument("--out-dir", default=os.environ.get("CFP_CUSTOMER_SNAPSHOTS", ""),
                    help="PRIVATE directory for snapshots; never a public repo")
    ap.add_argument("--source-url", default="", help="the sheet URL, recorded in the manifest")
    ap.add_argument("--note", default="", help="free text recorded with this snapshot")
    a = ap.parse_args()

    if not a.out_dir:
        print("ERROR: --out-dir (or CFP_CUSTOMER_SNAPSHOTS) is required.\n"
              "  These are the customer's data and this repo is public - there is deliberately\n"
              "  no default. Point it at the private working area.")
        return 2

    src = Path(a.csv)
    if not src.exists():
        print(f"ERROR: no such file: {src}")
        return 2

    headers, n_rows, present = read_shape(src)
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        print(f"REFUSED: {src.name} does not look like a customer sheet - missing {missing}.\n"
              f"  Found {len(headers)} column(s): {headers[:8]}\n"
              "  A sign-in redirect or the wrong tab produces exactly this, and storing it\n"
              "  would read next week as the customer deleting their whole list.")
        return 3

    out = Path(a.out_dir) / a.client
    out.mkdir(parents=True, exist_ok=True)
    # A snapshot is never overwritten, but two runs inside the same SECOND are a naming
    # collision rather than a reason to fail - so disambiguate instead of refusing. Failing
    # here would mean the second, later, more correct copy is the one thrown away.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = out / f"{a.client}_{stamp}.csv"
    n = 2
    while dest.exists():
        dest = out / f"{a.client}_{stamp}-{n}.csv"
        n += 1

    # Rewrite rather than copy, so credential columns never reach the disk. The file we hash and
    # store is the redacted one - hashing the original would report a digest for bytes we
    # deliberately did not keep.
    secret_idx = [i for i, h in enumerate(headers) if is_secret(h)]
    carried = write_redacted(src, dest, secret_idx)
    if secret_idx:
        cols = [headers[i] for i in secret_idx]
        print(f"  REDACTED {cols} - credential columns are never stored"
              + (f"\n  *** {carried} value(s) were present and have NOT been written. Check "
                 "whether the customer is keeping live credentials in the sheet. ***"
                 if carried else " (all empty in this export)"))

    digest = sha256(dest)
    manifest = out / "manifest.jsonl"
    prior = []
    if manifest.exists():
        with open(manifest, encoding="utf-8") as fh:
            prior = [json.loads(line) for line in fh if line.strip()]

    entry = {
        "client": a.client, "taken_at": datetime.now().isoformat(timespec="seconds"),
        "file": dest.name, "sha256": digest, "bytes": dest.stat().st_size,
        "data_rows": n_rows, "columns": headers, "column_classes": present,
        "redacted_columns": [headers[i] for i in secret_idx],
        "redacted_values_dropped": carried,
        "source_url": a.source_url, "source_file": str(src), "note": a.note,
    }
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    print(f"snapshot   {dest}")
    print(f"  sha256   {digest[:16]}...")
    print(f"  rows     {n_rows} data row(s), {len(headers)} column(s)")
    print(f"  owned    customer {len(present['customer_owned'])}, "
          f"evidence {len(present['evidence'])}, request {len(present['request'])}")

    same = [p for p in prior if p["client"] == a.client]
    if not same:
        print("\n  FIRST SNAPSHOT for this client. Nothing to compare against yet - that is the\n"
              "  point of taking it. Next week's run has a baseline for the first time.")
    else:
        last = same[-1]
        if last["sha256"] == digest:
            print(f"\n  IDENTICAL to {last['file']} (taken {last['taken_at'][:10]}) - the sheet "
                  "has not changed.")
        else:
            d = n_rows - last["data_rows"]
            print(f"\n  CHANGED since {last['file']} (taken {last['taken_at'][:10]}): "
                  f"{n_rows} rows vs {last['data_rows']} ({d:+d}).")
            gone = [c for c in last["columns"] if c not in headers]
            new = [c for c in headers if c not in last["columns"]]
            if gone:
                print(f"  COLUMNS REMOVED: {gone} - a diff keyed on these will silently skip.")
            if new:
                print(f"  columns added: {new}")
            print("  Cell-level diff is stage 2 and is not built yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
