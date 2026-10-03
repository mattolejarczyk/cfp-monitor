"""Write the CONFIRMED answer key from the operator-verified pins: docs/qa/answer-key.csv.

    python scripts/answer_key_from_pins.py [--out docs/qa/answer-key.csv]

The pin ledger (docs/operations/pinned_rows.json) is the one place a person's verification is entered (QA-REGISTER.md C14). This turns it into the key every method is scored on:
one line per event and field with the confirmed value, who confirmed it, when, and the pages. A pinned blank is a line too ("the page states nothing"). The draft with our claims and
page proof status for all 40 benchmark events stays in docs/qa/answer-key-DRAFT.csv; the benchmark's deadline key stays in docs/agents/results/01-benchmark-key.csv. Reads only the pins."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.pinned_rows import load_pins                      # noqa: E402

COLS = ["event", "canonical", "field", "confirmed_value", "page_states_nothing", "confirmed_by", "confirmed_on", "pages", "why"]


def key_rows(pins: list[dict]) -> list[dict]:
    rows = []
    for p in pins:
        for field, value in p.get("set", {}).items():
            if field in ("DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED"):
                continue                                              # evidence of a deadline, not a separate fact
            rows.append({"event": p.get("event", ""), "canonical": p["canonical"], "field": field, "confirmed_value": value, "page_states_nothing": "yes" if value == "" else "",
                         "confirmed_by": p.get("by", ""), "confirmed_on": p.get("ruled_on", ""), "pages": " ; ".join(p.get("links", [])), "why": p.get("why", "")})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "qa" / "answer-key.csv"))
    a = ap.parse_args()
    rows = key_rows(load_pins())
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} confirmed facts for {len({r['canonical'] for r in rows})} events -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
