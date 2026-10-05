"""The answer key's confidence TIERS, and who may be scored against which (ACT-21, operator decision ACT-04 of 2026-10-05).

    from scripts.answer_key import load_key, reader_key, grounded_key, assert_reader_tier, page_proven_rows

TIERS (column `tier` of docs/qa/answer-key.csv):
  person-confirmed     a person read the event's own page and ruled (the pins, docs/operations/pinned_rows.json).
  page-proven-agrees   no person yet: the cheap reader proved the value on the event's own page with a verbatim quote (the code-checked quote, pass_lib.accept)
                       AND it equals what we ship. Two independent routes agree; it is still not a ruling. Source: docs/qa/answer-key-CANDIDATES.csv, status 'agree'.
WHO IS SCORED ON WHAT (this is the decision; it avoids a circular score):
  the READER (read-the-page pass, finder+reader) is scored ONLY on person-confirmed facts: it is never graded against facts it helped confirm.
  the GROUNDED call (the research we ship) may be scored on BOTH tiers.
Pure functions plus one reader of the key file. Nothing here calls a model or the network."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / "docs" / "qa" / "answer-key.csv"

PERSON = "person-confirmed"
PAGE = "page-proven-agrees"
TIERS = (PERSON, PAGE)
READER_TIERS = (PERSON,)
GROUNDED_TIERS = (PERSON, PAGE)
COLS = ["event", "canonical", "field", "confirmed_value", "tier", "page_states_nothing", "confirmed_by", "confirmed_on", "pages", "why", "quote"]


def _tier(row: dict) -> str:
    """A row from a file written before the tiers existed has no tier: every line in it came from a pin, so it is person-confirmed. An UNKNOWN tier word is never trusted."""
    t = (row.get("tier") or "").strip()
    return t if t else PERSON


def load_key(path: Path | str = KEY_FILE, tiers: tuple[str, ...] = TIERS) -> list[dict]:
    """The key lines whose tier is in `tiers`. A line with a tier this module does not know is refused loudly, not skipped."""
    out = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            t = _tier(r)
            if t not in TIERS:
                raise ValueError(f"unknown tier {t!r} in {path} for {r.get('event')!r} {r.get('field')!r}")
            if t in tiers:
                out.append(dict(r, tier=t))
    return out


def reader_key(path: Path | str = KEY_FILE) -> list[dict]:
    """What the READER may be scored on: person-confirmed facts only."""
    return load_key(path, READER_TIERS)


def grounded_key(path: Path | str = KEY_FILE) -> list[dict]:
    """What the GROUNDED call may be scored on: both tiers."""
    return load_key(path, GROUNDED_TIERS)


def assert_reader_tier(facts: list[dict], what: str = "reader score") -> None:
    """Refuse to score the reader on a fact that is not person-confirmed. A fact with no `tier` key is taken as person-confirmed (it came from the pins)."""
    bad = [f for f in facts if (f.get("tier") or PERSON) != PERSON]
    if bad:
        raise ValueError(f"{what}: {len(bad)} fact(s) are not person-confirmed (first: {bad[0].get('event')!r} {bad[0].get('field')!r}, tier {bad[0].get('tier')!r}); "
                         "the reader is scored only on person-confirmed facts (ACT-04)")


def person_confirmed_events(rows: list[dict]) -> set[str]:
    """Normalised event names that have at least one person-confirmed line: the ones the candidate reader need not look at again."""
    return {re.sub(r"[^a-z0-9]+", " ", (r.get("event") or "").lower()).strip() for r in rows if _tier(r) == PERSON}


def page_proven_rows(candidates: list[dict], name_to_canonical: dict[str, str], person_rows: list[dict]) -> list[dict]:
    """Key lines for tier page-proven-agrees from answer-key-CANDIDATES.csv rows. Only status 'agree' WITH a quote counts. A fact a person already confirmed
    (same canonical id and field) is never duplicated at the lower tier. A candidate whose event we cannot map to a canonical id is kept with a blank canonical and
    the event name (it is reported by the CLI) so nothing is silently lost."""
    have = {(r.get("canonical", ""), r.get("field", "")) for r in person_rows}
    out = []
    for c in candidates:
        if (c.get("status") or "").strip() != "agree" or not (c.get("quote") or "").strip():
            continue
        canon = name_to_canonical.get((c.get("event") or "").strip().lower(), "")
        if canon and (canon, c["field"]) in have:
            continue
        out.append({"event": c["event"], "canonical": canon, "field": c["field"], "confirmed_value": c.get("reader_value", ""), "tier": PAGE, "page_states_nothing": "",
                    "confirmed_by": "", "confirmed_on": "", "pages": c.get("pages", ""), "why": "the page states it with a verbatim quote and it equals our shipped value; no person has ruled",
                    "quote": c["quote"]})
    return out


def tier_counts(rows: list[dict]) -> dict[str, int]:
    out = {t: 0 for t in TIERS}
    for r in rows:
        out[_tier(r)] = out.get(_tier(r), 0) + 1
    return out
