"""Write the answer key: docs/qa/answer-key.csv, with a confidence TIER on every line (scripts/answer_key.py, ACT-21).

    python scripts/answer_key_from_pins.py [--out docs/qa/answer-key.csv] [--candidates docs/qa/answer-key-CANDIDATES.csv | --no-candidates]

Tier 1, person-confirmed: the pin ledger (docs/operations/pinned_rows.json) is the one place a person's verification is entered (QA-REGISTER.md C14). One line per event and field with
the confirmed value, who confirmed it, when, and the pages. A pinned blank is a line too ("the page states nothing").
Tier 2, page-proven-agrees: the reader's candidates (experiments/read_the_page_pass/key_candidates.py) whose value is proven on the page with a verbatim quote AND equals what we ship.
No person has ruled on these. The READER is scored only on tier 1 (it is never graded against facts it helped confirm); the grounded call may use both.
The draft with our claims and page proof status for all 40 benchmark events stays in docs/qa/answer-key-DRAFT.csv; the benchmark's deadline key stays in
docs/agents/results/01-benchmark-key.csv. Reads only the pins and the candidates file (and, to map an event name to our id, the approved files and seed sheets, read-only)."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.answer_key import COLS, PAGE, PERSON, page_proven_rows, tier_counts     # noqa: E402
from scripts.pinned_rows import load_pins                                           # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")


def key_rows(pins: list[dict]) -> list[dict]:
    rows = []
    for p in pins:
        for field, value in p.get("set", {}).items():
            if field in ("DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED"):
                continue                                              # evidence of a deadline, not a separate fact
            rows.append({"event": p.get("event", ""), "canonical": p["canonical"], "field": field, "confirmed_value": value, "tier": PERSON,
                         "page_states_nothing": "yes" if value == "" else "",
                         "confirmed_by": p.get("by", ""), "confirmed_on": p.get("ruled_on", ""), "pages": " ; ".join(p.get("links", [])), "why": p.get("why", ""), "quote": ""})
    return rows


def name_to_canonical(markets_dir: Path = MARKETS) -> dict[str, str]:
    """CONFERENCE name (lower case) -> our canonical id, from the approved files (upstream EVENT_ID) through identity.seed_map. Read-only; {} when the files are not there."""
    out: dict[str, str] = {}
    try:
        from src.cfp_monitor.identity import seed_map, to_canonical
        from scripts.board_metrics import LIVE_DB
        up_to_canon, _roots = seed_map(str(LIVE_DB))
        for m in ("Cybersecurity", "Utility"):
            with open(markets_dir / f"{m}_audited.final.csv", encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    if r.get("EVENT_ID"):
                        out[(r.get("CONFERENCE") or "").strip().lower()] = to_canonical(r["EVENT_ID"], up_to_canon)
    except (OSError, ImportError):
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "qa" / "answer-key.csv"))
    ap.add_argument("--candidates", default=str(ROOT / "docs" / "qa" / "answer-key-CANDIDATES.csv"))
    ap.add_argument("--no-candidates", action="store_true", help="person-confirmed lines only")
    a = ap.parse_args()
    rows = key_rows(load_pins())
    unmapped = 0
    if not a.no_candidates and Path(a.candidates).exists():
        with open(a.candidates, encoding="utf-8", newline="") as fh:
            cands = list(csv.DictReader(fh))
        extra = page_proven_rows(cands, name_to_canonical(), rows)
        unmapped = sum(1 for r in extra if not r["canonical"])
        rows += extra
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    tc = tier_counts(rows)
    print(f"{len(rows)} facts for {len({r['canonical'] or r['event'] for r in rows})} events -> {a.out}  (person-confirmed {tc[PERSON]}, page-proven-agrees {tc[PAGE]}; {unmapped} page-proven lines with no canonical id)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
