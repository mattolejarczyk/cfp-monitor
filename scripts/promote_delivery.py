"""Step 4a: promote an ACCEPTED delivery to <Market>_audited.final.csv, with a signed record.

Replaces the manual `cp` in runbook 4b. It REFUSES to promote anything the gate did not
ACCEPT, backs up the file currently published, copies the accepted delivery into place, and
writes the promotion manifest the Monday build reads to tell a fresh delivery from last
cycle's. See src/cfp_monitor/publish_guard.py for what the manifest binds and why.

Usage:
    python scripts/promote_delivery.py \
        --delivery ".../Cybersecurity_audited.csv" \
        --accept-json ".../Cybersecurity_accept.json" \
        --market Cybersecurity

Get the acceptance json from the gate first (a NETWORKED run, never --no-network):
    python scripts/accept_delivery.py ".../Cybersecurity_audited.csv" --json ".../Cybersecurity_accept.json"
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cfp_monitor.publish_guard import acceptance_verdict, write_manifest  # noqa: E402

MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote an ACCEPTED delivery to its published final.csv.")
    ap.add_argument("--delivery", required=True, help="the ACCEPTED delivery CSV to publish")
    ap.add_argument("--accept-json", required=True, help="accept_delivery.py --json output for it")
    ap.add_argument("--market", required=True, help="Cybersecurity or Utility")
    ap.add_argument("--final", help="target final.csv (default: <markets-dir>/<Market>_audited.final.csv)")
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--force", action="store_true",
                    help="promote despite a non-ACCEPTED verdict; the manifest records the REAL "
                         "verdict, so the build still refuses it - use only to stage a file by hand")
    a = ap.parse_args()

    delivery = Path(a.delivery)
    if not delivery.exists():
        print(f"ERROR: delivery not found: {delivery}")
        return 1
    final = Path(a.final) if a.final else Path(a.markets_dir) / f"{a.market}_audited.final.csv"

    verdict, reason = acceptance_verdict(a.accept_json, delivery.name)
    print(f"acceptance for {delivery.name}: {verdict} - {reason}")
    if verdict != "ACCEPTED" and not a.force:
        print("\nREFUSING to promote: only an ACCEPTED delivery may be published.")
        print("  Run the gate networked (no --no-network) and promote the file it accepts.")
        return 2

    if final.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = final.with_name(f"{final.stem}.pre-promote-{stamp}{final.suffix}")
        shutil.copy2(final, backup)
        print(f"backed up current published file -> {backup.name}")

    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(delivery, final)
    m = write_manifest(final, a.market, delivery, a.accept_json, verdict)
    print(f"promoted {delivery.name} -> {final.name}")
    print(f"  verdict {verdict}  sha256 {m['promoted_sha256'][:16]}...  at {m['promoted_at']}")
    print(f"  manifest written: {final.name}{'.promoted.json'}")
    if a.force and verdict != "ACCEPTED":
        print("  NOTE: --force used; the build will still REFUSE this file (verdict is not ACCEPTED).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
