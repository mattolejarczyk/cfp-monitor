"""A snapshot must be honest about what it stored, and must refuse what it cannot recognise.

This is stage 0 of the customer reconciliation process, and the whole process rests on it: every
later stage answers a question about CHANGE, which needs last week's copy to be trustworthy. The
failure that matters is not a crash - it is storing a sign-in page or a truncated export, which
next week reads as the customer having deleted their list.
"""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts" / "snapshot_customer_sheet.py"
_spec = importlib.util.spec_from_file_location("_scs", SCRIPT)
scs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scs)

HEADERS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "EVENT START DATE", "LATEST UPDATE",
           "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY", "STATUS",
           "STATUS DETAILS", "SUBMISSION URL", "SPEAKER & ABSTRACTS SUBMITTED"]


def _sheet(path, rows, headers=None, bom=True):
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, "w", encoding=enc, newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers or HEADERS)
        w.writerows(rows)
    return path


def _row(name="Some Conference 2027", deadline="2027-01-15", status="Submitted"):
    return [name, "https://example.org/", "Boston, USA", "2027-05-01", "2026-08-01",
            deadline, "Verified", "", status, "4/28 - emailed organiser", "", ""]


def _run(csv_path, client, out_dir, expect=0):
    r = subprocess.run([sys.executable, str(SCRIPT), "--csv", str(csv_path),
                        "--client", client, "--out-dir", str(out_dir)],
                       capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == expect, r.stdout + r.stderr
    return r.stdout


def test_it_stores_the_file_and_records_a_hash(tmp_path):
    src = _sheet(tmp_path / "export.csv", [_row(), _row("Another 2027")])
    out = tmp_path / "snaps"
    _run(src, "utility", out)
    entries = [json.loads(x) for x in (out / "utility" / "manifest.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    assert len(entries) == 1
    e = entries[0]
    assert e["data_rows"] == 2
    assert len(e["sha256"]) == 64
    assert (out / "utility" / e["file"]).exists()


def test_a_google_sheets_bom_does_not_corrupt_the_first_column(tmp_path):
    """The 2026-07-09 lesson: a BOM on line one silently corrupted the first key in .env and
    cost a day. Google's CSV export always carries one, and CONFERENCE is the join column."""
    src = _sheet(tmp_path / "export.csv", [_row()], bom=True)
    headers, n, _present = scs.read_shape(src)
    assert headers[0] == "CONFERENCE", f"BOM leaked into the header: {headers[0]!r}"
    assert n == 1


def test_it_refuses_a_file_that_is_not_a_customer_sheet(tmp_path):
    """A sign-in redirect or the wrong tab. Storing it would read next week as the customer
    deleting their entire list."""
    src = tmp_path / "notasheet.csv"
    src.write_text("<html><body>Sign in to continue</body></html>", encoding="utf-8")
    out = tmp_path / "snaps"
    stdout = _run(src, "utility", out, expect=3)
    assert "REFUSED" in stdout
    assert not (out / "utility").exists(), "nothing may be written when the file is refused"


def test_it_refuses_the_right_spreadsheet_with_the_wrong_columns(tmp_path):
    src = _sheet(tmp_path / "export.csv", [["a", "b"]], headers=["Notes", "Owner"])
    stdout = _run(src, "utility", tmp_path / "snaps", expect=3)
    assert "REFUSED" in stdout and "CONFERENCE" in stdout


def test_out_dir_has_no_default_because_this_repo_is_public(tmp_path):
    """The customer's sheet is their asset. The golden-master delivery snapshot lives in the
    private area for the same reason; a default pointing anywhere here would be a leak."""
    src = _sheet(tmp_path / "export.csv", [_row()])
    r = subprocess.run([sys.executable, str(SCRIPT), "--csv", str(src), "--client", "utility"],
                       capture_output=True, text=True, cwd=str(ROOT),
                       env={"PATH": "", "SYSTEMROOT": "C:\\Windows"})
    assert r.returncode == 2
    assert "no default" in r.stdout


def test_a_second_snapshot_never_overwrites_the_first(tmp_path):
    """Including two inside the same second, which is a naming collision and not a reason to
    fail - refusing there throws away the later, more correct copy."""
    src = _sheet(tmp_path / "export.csv", [_row()])
    out = tmp_path / "snaps"
    _run(src, "utility", out)
    _sheet(src, [_row(), _row("Newly Added 2027")])
    _run(src, "utility", out)
    files = sorted((out / "utility").glob("utility_*.csv"))
    assert len(files) == 2, "a snapshot is append-only; losing one loses the baseline"
    bodies = {f.read_text(encoding="utf-8-sig") for f in files}
    assert len(bodies) == 2, "the second snapshot must be the NEW content, not a copy"


def test_it_reports_row_movement_against_the_previous_snapshot(tmp_path):
    src = _sheet(tmp_path / "export.csv", [_row(), _row("B 2027")])
    out = tmp_path / "snaps"
    assert "FIRST SNAPSHOT" in _run(src, "utility", out)
    _sheet(src, [_row()])
    stdout = _run(src, "utility", out)
    assert "CHANGED" in stdout and "1 rows vs 2" in stdout and "-1" in stdout


def test_an_unchanged_sheet_says_so_rather_than_inventing_news(tmp_path):
    src = _sheet(tmp_path / "export.csv", [_row()])
    out = tmp_path / "snaps"
    _run(src, "utility", out)
    stdout = _run(src, "utility", out)
    assert "IDENTICAL" in stdout


def test_a_removed_column_is_called_out_not_silently_absorbed(tmp_path):
    """A diff keyed on a column that vanished skips silently - the same shape as the field that
    was checked while four others were rendered."""
    src = _sheet(tmp_path / "export.csv", [_row()])
    out = tmp_path / "snaps"
    _run(src, "utility", out)
    trimmed = [h for h in HEADERS if h != "STATUS DETAILS"]
    with open(src, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(trimmed)
        w.writerow(_row()[:9] + _row()[10:])
    stdout = _run(src, "utility", out)
    assert "COLUMNS REMOVED" in stdout and "STATUS DETAILS" in stdout


def test_credentials_are_never_written_to_disk(tmp_path):
    """Both real sheets carry LOGIN and PW columns. They are empty today, and this job copies
    the sheet into a git repo every week - so the first time one is filled we would commit it,
    permanently. Empty-today is not a safety argument."""
    hdr = HEADERS + ["NOTES", "LOGIN", "PW"]
    with open(tmp_path / "export.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(hdr)
        w.writerow(_row() + ["a note", "speaker@example.org", "hunter2-SECRET"])
    out = tmp_path / "snaps"
    stdout = _run(tmp_path / "export.csv", "utility", out)

    stored = next((out / "utility").glob("utility_*.csv")).read_text(encoding="utf-8-sig")
    assert "hunter2-SECRET" not in stored
    assert "speaker@example.org" not in stored
    assert scs.REDACTED in stored
    assert "a note" in stored, "only the credential columns are redacted"
    assert "LOGIN" in stored and "PW" in stored, "columns stay so the diff still lines up"
    assert "REDACTED" in stdout and "2 value(s) were present" in stdout


def test_redaction_survives_a_misspelled_header(tmp_path):
    """The two real sheets already disagree on spelling - NOTIFCATION vs NOTIFICATION - so an
    exact, case-sensitive match is one typo away from storing a password."""
    assert scs.is_secret(" login ") and scs.is_secret("PW") and scs.is_secret("Password")
    assert not scs.is_secret("STATUS DETAILS")


def test_the_hash_describes_the_bytes_we_actually_kept(tmp_path):
    """Hashing the original would report a digest for content we deliberately did not store."""
    hdr = HEADERS + ["PW"]
    with open(tmp_path / "export.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(hdr)
        w.writerow(_row() + ["secret"])
    out = tmp_path / "snaps"
    _run(tmp_path / "export.csv", "utility", out)
    e = json.loads((out / "utility" / "manifest.jsonl").read_text().strip())
    stored = next((out / "utility").glob("utility_*.csv"))
    assert e["sha256"] == scs.sha256(stored)
    assert e["redacted_columns"] == ["PW"] and e["redacted_values_dropped"] == 1


def test_clients_are_kept_apart(tmp_path):
    out = tmp_path / "snaps"
    _run(_sheet(tmp_path / "u.csv", [_row()]), "utility", out)
    _run(_sheet(tmp_path / "a.csv", [_row(), _row("B")]), "arnica", out)
    assert (out / "utility" / "manifest.jsonl").exists()
    assert (out / "arnica" / "manifest.jsonl").exists()
    u = [json.loads(x) for x in (out / "utility" / "manifest.jsonl").read_text().splitlines() if x.strip()]
    assert len(u) == 1 and u[0]["data_rows"] == 1
