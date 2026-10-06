"""Put the events a customer tracks onto our research INPUT list (ACT-51, failure point A14). Report-only unless --apply.

    python scripts/add_customer_rows.py --classified docs/qa/customer-unmatched-classified-20261003.csv [--markets-dir <dir>] [--min-start 2026-10-11] [--apply]

WHY. The customer's sheets are the definition of the job: any event on them must be researched. The weekly intake only reads their status, so a row they add never reached the queue (found 2026-10-05:
84 customer rows with no match, 57 of them still ahead). `scripts/customer_coverage.py`-style classification (ACT-44) says which rows are class C (not held, still ahead); this appends each as a new row of
`<Market>_input.csv` (arnica -> Cybersecurity, utility -> Utility).

WHAT A NEW ROW CARRIES. CONFERENCE (the customer's name), CONFERENCE URL (the page the classification confirmed, else the customer's), LOCATION (the customer's), START DATE (the page's date when confirmed,
else the customer's), EDITION (its year), Market, RESEARCH STATUS 'Needs Verification'. EVENT_ID_CANON is left BLANK on purpose: identity is upstream's (contract 5.4, we never mint ids). A blank-id row is
researched but never loaded as a new event (weekend_import holds it back, scripts/stamp_input_ids.py) until upstream supplies the id and it is stamped; the cost of that wait is one research pass.

SAFETY. Never edits or removes an existing row; skips a name already on the list (exact, case-insensitive) and an event that starts before --min-start (research cannot help it); an event with NO date is added (research is what finds the date); a timestamped backup
`<input>.pre-customerrows-<stamp>.bak.csv` is written first; the file is written to .tmp with the original BOM and line endings, QUOTE_ALL, read back and proved to equal the old rows plus exactly the new ones;
then os.replace. Report by default."""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
SHEET_MARKET = {"arnica": "Cybersecurity", "utility": "Utility"}


def us_date(iso: str) -> str:
    """2027-03-29 -> 3/29/2027 (the input lists' format); anything else is returned unchanged."""
    try:
        d = datetime.strptime((iso or "").strip(), "%Y-%m-%d")
    except ValueError:
        return (iso or "").strip()
    return f"{d.month}/{d.day}/{d.year}"


def iso_of(text: str) -> str:
    for f in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime((text or "").strip(), f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


def new_row(r: dict, cols: list[str], market: str) -> dict:
    confirmed = (r.get("page_confirmed") or "") == "yes"
    start_iso = iso_of(r.get("page_start_date")) if confirmed and iso_of(r.get("page_start_date")) else iso_of(r.get("customer_start"))
    row = {c: "" for c in cols}
    row["CONFERENCE"] = (r["conference"] or "").strip()
    row["CONFERENCE URL"] = ((r.get("evidence_url") if confirmed and r.get("evidence_url") else r.get("customer_url")) or "").strip()
    row["LOCATION"] = (r.get("customer_location") or "").strip()
    row["START DATE"] = us_date(start_iso)
    row["EDITION"] = start_iso[:4]
    row["Market"] = market
    row["RESEARCH STATUS"] = "Needs Verification"
    return row


def plan(classified: list[dict], inputs: dict[str, list[dict]], cols: dict[str, list[str]], min_start: str) -> tuple[dict[str, list[dict]], list[tuple[str, str]]]:
    """({market: [new rows]}, [(conference, why skipped)])."""
    have = {m: {(r["CONFERENCE"] or "").strip().lower() for r in rows} for m, rows in inputs.items()}
    add: dict[str, list[dict]] = {m: [] for m in inputs}
    skipped: list[tuple[str, str]] = []
    for r in classified:
        if r.get("class") != "C":
            continue
        market = SHEET_MARKET.get((r.get("sheet") or "").lower())
        if market not in inputs:
            skipped.append((r["conference"], f"sheet {r.get('sheet')!r} has no market here"))
            continue
        nr = new_row(r, cols[market], market)
        name = nr["CONFERENCE"].lower()
        start = iso_of(nr["START DATE"])
        if name in have[market] or any(name == (x["CONFERENCE"] or "").strip().lower() for x in add[market]):
            skipped.append((nr["CONFERENCE"], "already on the input list"))
        elif start and start < min_start:
            skipped.append((nr["CONFERENCE"], f"starts {start}, before {min_start}: research cannot help it"))
        else:
            add[market].append(nr)
    return add, skipped


def read_input(path: Path) -> tuple[list[str], list[dict], bool, bool]:
    raw = path.read_bytes()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames), list(rd), raw.startswith(b"\xef\xbb\xbf"), b"\r\n" in raw


def write_with_proof(path: Path, cols: list[str], old: list[dict], new: list[dict], bom: bool, crlf: bool) -> Path:
    """Backup, write old + new, read back and prove; returns the backup path. Raises (original untouched) on any difference."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = path.with_name(path.name.replace(".csv", "") + f".pre-customerrows-{stamp}.bak.csv")
    shutil.copy2(path, bak)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(old + new)
    with open(tmp, encoding="utf-8-sig", newline="") as fh:
        back = list(csv.DictReader(fh))
    if back[:len(old)] != old or len(back) != len(old) + len(new) or [r["CONFERENCE"] for r in back[len(old):]] != [r["CONFERENCE"] for r in new]:
        tmp.unlink(missing_ok=True)
        raise AssertionError(f"{path.name}: read-back differs from old rows plus the new ones; original left in place")
    os.replace(tmp, path)
    return bak


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--classified", required=True)
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--min-start", default="2026-10-11", help="skip events starting before this date (ISO)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    with open(a.classified, encoding="utf-8-sig", newline="") as fh:
        classified = list(csv.DictReader(fh))
    files, inputs, cols = {}, {}, {}
    for m in ("Cybersecurity", "Utility"):
        p = Path(a.markets_dir) / f"{m}_input.csv"
        files[m] = (p, *read_input(p))
        cols[m], inputs[m] = files[m][1], files[m][2]
    add, skipped = plan(classified, inputs, cols, a.min_start)
    for m, rows in add.items():
        print(f"{m}: {len(inputs[m])} rows now, {len(rows)} to add")
        for r in rows:
            print(f"   + {r['CONFERENCE'][:52]:52s} {r['START DATE']:11s} {r['CONFERENCE URL'][:60]}")
    for name, why in skipped:
        print(f"   SKIP {name[:48]:48s} {why}")
    if not a.apply:
        print("\nreport only; add --apply to write (backups first)")
        return 0
    for m, rows in add.items():
        if rows:
            p, c, old, bom, crlf = files[m]
            bak = write_with_proof(p, c, old, rows, bom, crlf)
            print(f"{p.name}: {len(rows)} row(s) appended, proved old rows unchanged; backup {bak.name}")
    print("\nNEXT: send note 30 so upstream supplies the ids; stamp them in EVENT_ID_CANON when they arrive; log in OPERATOR-EDITS-LOG.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
