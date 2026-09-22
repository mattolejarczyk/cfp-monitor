"""Step 4a guard: the build must publish the delivery the gate ACCEPTED, not a stale one.

WHY THIS EXISTS. `weekly_deliverable.py` reads `<Market>_audited.final.csv` by a hardcoded
name, so a cycle where nobody PROMOTED the freshly-accepted delivery publishes LAST week's
file - and every other check stays green. It happened on 2026-09-14: the customer got a page
two weeks and two accepted deliveries out of date. The promote step (runbook 4b) was a manual
`cp` with no record, and nothing downstream could tell a fresh delivery from a stale one.

QUALITY BY DESIGN. Promotion now leaves a signed manifest beside the published file, and the
build refuses a `final.csv` that is not a fresh, accepted, untampered promotion. The refusal
rides the existing "nothing publishes from a DEGRADED run" path - the build does not silently
ship; it goes DEGRADED and says WHICH market and WHY. Diagnostic that ends in a decision, not
a number nobody reads.

The manifest binds three facts the build cannot otherwise see:
  - the delivery was ACCEPTED by the gate (verdict, from accept_delivery.py --json);
  - the published bytes are exactly what was promoted (sha256), so a later hand-edit is caught;
  - it was promoted THIS cycle (promoted_at), so last week's file is caught as stale.
"""
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

MANIFEST_SUFFIX = ".promoted.json"


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def acceptance_verdict(accept_json_path, delivery_name):
    """(verdict, reason) for one delivery basename from an accept_delivery.py --json file.

    Recomputes the gate's own three-way verdict from the per-check results, so this cannot
    drift from accept_delivery.py: ACCEPTED only when every check ran and passed; a SKIPPED
    failure (a --no-network run) is INCOMPLETE, not acceptance.
    verdict in {ACCEPTED, REJECTED, INCOMPLETE, NOT_FOUND, UNREADABLE}.
    """
    p = Path(accept_json_path)
    if not p.exists():
        return "UNREADABLE", f"acceptance json not found: {p.name}"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:                                               # noqa: BLE001
        return "UNREADABLE", f"acceptance json unreadable: {e}"
    checks = payload.get(delivery_name)
    if checks is None:
        return "NOT_FOUND", f"acceptance json does not name {delivery_name}"

    def _is_skip(c):
        f = c.get("failures") or []
        return bool(f) and str(f[0]).startswith("SKIPPED")

    failed = [c for c in checks if not c.get("passed") and not _is_skip(c)]
    skipped = [c for c in checks if not c.get("passed") and _is_skip(c)]
    if failed:
        return "REJECTED", f"{len(failed)} check(s) failed"
    if skipped:
        return "INCOMPLETE", f"{len(skipped)} check(s) not run (a --no-network gate is not acceptance)"
    return "ACCEPTED", "every check ran and passed"


def manifest_path(final_csv) -> Path:
    return Path(str(final_csv) + MANIFEST_SUFFIX)


def write_manifest(final_csv, market, source_delivery, accept_json, verdict, promoted_at=None):
    """Stamp the promotion record beside the published file. Returns the manifest dict."""
    final_csv = Path(final_csv)
    m = {
        "market": market,
        "source_delivery": str(source_delivery),
        "acceptance_json": str(accept_json),
        "acceptance_verdict": verdict,
        "promoted_sha256": sha256_file(final_csv),
        "promoted_at": (promoted_at or datetime.now()).isoformat(timespec="seconds"),
    }
    manifest_path(final_csv).write_text(json.dumps(m, indent=2), encoding="utf-8")
    return m


def check_publish_fresh(final_csv, today=None, max_age_days=4):
    """(ok, reason). True only when final.csv is a fresh, ACCEPTED, untampered promotion.

    Refuses, each with a reason the build surfaces:
      - no file, or no manifest (a bare `cp` that skipped the guard);
      - promoted from a delivery that was not ACCEPTED;
      - bytes changed since promotion (hash mismatch - hand-edited after promote);
      - promoted more than max_age_days ago (a cycle was skipped; this is last cycle's file).
    """
    final_csv = Path(final_csv)
    today = today or date.today()
    if not final_csv.exists():
        return False, f"{final_csv.name} does not exist"
    mp = manifest_path(final_csv)
    if not mp.exists():
        return False, (f"{final_csv.name} has no promotion manifest - it was not promoted through "
                       f"promote_delivery.py, so its provenance is unknown")
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as e:                                               # noqa: BLE001
        return False, f"{mp.name} is unreadable: {e}"
    if m.get("acceptance_verdict") != "ACCEPTED":
        return False, (f"{final_csv.name} was promoted from a "
                       f"{m.get('acceptance_verdict', 'UNKNOWN')} delivery, not an ACCEPTED one")
    if sha256_file(final_csv) != m.get("promoted_sha256"):
        return False, f"{final_csv.name} has changed since it was promoted (hash mismatch)"
    try:
        promoted = datetime.fromisoformat(m["promoted_at"]).date()
    except Exception:                                                    # noqa: BLE001
        return False, f"{mp.name} has no valid promoted_at"
    age = (today - promoted).days
    if age < 0:
        return False, f"{final_csv.name} promoted_at is in the future ({promoted})"
    if age > max_age_days:
        return False, (f"{final_csv.name} was promoted {age} days ago ({promoted}), older than the "
                       f"{max_age_days}-day window - a cycle was likely skipped and this is stale")
    return True, f"fresh: ACCEPTED, promoted {promoted} ({age}d ago), bytes match"
