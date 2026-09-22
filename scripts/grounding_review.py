"""Review-step triage over a run's grounding trail: concise, decision-ready actions.

Reads a `<output>.grounding.jsonl` and prints, per flagged row, what a person should do -
verify a possibly-composed citation, or re-run a stub. Advisory (exit 0 always); it routes
work to the review step, it does not gate. Logic in src/cfp_monitor/grounding_review.py.

Usage:
    python scripts/grounding_review.py ".../Cybersecurity_audited.grounding.jsonl"
    python scripts/grounding_review.py ".../Markets"      # newest *.grounding.jsonl in a folder
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.cfp_monitor.grounding_review import review_file  # noqa: E402


def _resolve(target: Path) -> Path | None:
    if target.is_dir():
        trails = sorted(target.glob("*.grounding.jsonl"), key=lambda p: p.stat().st_mtime)
        return trails[-1] if trails else None
    return target if target.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Decision-ready review of a grounding trail.")
    ap.add_argument("path", help="a .grounding.jsonl file, or a folder to take the newest from")
    a = ap.parse_args()

    jsonl = _resolve(Path(a.path))
    if jsonl is None:
        print(f"No grounding trail found at {a.path}")
        return 1
    print(review_file(jsonl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
