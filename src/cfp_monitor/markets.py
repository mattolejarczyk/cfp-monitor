"""Market (industry) registry + list-filename parsing for batch runs.

Two jobs, deliberately kept together because they share one normalization rule:

1. A **controlled vocabulary** of markets. Industry must never be free-form or the
   dropdown fragments into Utility / Utilities / utility within a month. New markets are
   allowed only when they are genuinely new: an exact (normalized) match resolves to the
   existing canonical spelling, and a *near* match is refused unless explicitly forced.

2. Parsing a customer list filename into (market, list_type). Boilerplate tokens
   ("Conference", "Award", "List", "Global", "Industry", a year) are stripped; what remains
   is matched against the registry. A filename that does NOT match is left blank for a human
   to resolve - it is never guessed.
"""
from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher
from typing import Iterable, Optional

# Seed vocabulary, taken from the customer's own list filenames (their wording, not ours).
DEFAULT_MARKETS = [
    "Additive Manufacturing & 3D Printing",
    "Arnica",
    "Bioeconomy & Biofuels",
    "Biotech & MedTech",
    "Consumer Electronics",
    "Robotics",
    "Semiconductor",
    "Utility",
]

# Filename tokens that carry no market meaning.
_BOILERPLATE = {
    "conference", "conferences", "award", "awards", "list", "lists", "global",
    "industry", "industries", "cfp", "customer", "final", "copy", "v1", "v2",
}
_AWARD_WORDS = {"award", "awards"}
_CONF_WORDS = {"conference", "conferences"}

# Optional aliases: filename token -> canonical market. Lets a list keep its own filename
# while the registry shows a different label (e.g. "Arnica" -> "Cybersecurity") without a
# data migration. Keys are matched after normalization.
ALIASES: dict[str, str] = {}


def normalize(name: Optional[str]) -> str:
    """Comparison key: lowercase, drop everything that isn't a letter or digit.
    So 'Biotech & MedTech', 'biotech medtech' and 'Biotech_MedTech' all collapse together."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def parse_filename(filename: str) -> tuple[str, Optional[str]]:
    """Split a customer list filename into (market_candidate, list_type).

    list_type is 'Awards' | 'Conferences' | None. The market candidate is whatever survives
    after boilerplate/years/extensions are removed -- it is a CANDIDATE only; the caller must
    resolve it against the registry and leave it blank if it doesn't match.
    """
    stem = re.sub(r"\.(xlsx|xlsm|csv|txt)$", "", filename.strip(), flags=re.I)
    stem = re.sub(r"\(\d+\)", " ", stem)                 # drop "(3)" download suffixes
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", stem) if t]

    lowered = [t.lower() for t in tokens]
    list_type: Optional[str] = None
    if any(t in _AWARD_WORDS for t in lowered):
        list_type = "Awards"
    elif any(t in _CONF_WORDS for t in lowered):
        list_type = "Conferences"

    keep = [t for t in tokens
            if t.lower() not in _BOILERPLATE and not re.fullmatch(r"(19|20)\d{2}", t)]
    return " ".join(keep).strip(), list_type


class MarketRegistry:
    """The canonical market list, persisted in the same SQLite DB as everything else."""

    def __init__(self, db: sqlite3.Connection, seed: Optional[Iterable[str]] = None):
        self.db = db
        self.db.execute("CREATE TABLE IF NOT EXISTS industries ("
                        " name TEXT PRIMARY KEY, norm TEXT UNIQUE NOT NULL)")
        for name in (seed if seed is not None else DEFAULT_MARKETS):
            self.db.execute("INSERT OR IGNORE INTO industries (name, norm) VALUES (?,?)",
                            (name, normalize(name)))
        self.db.commit()

    def all(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT name FROM industries ORDER BY name")]

    def resolve(self, candidate: Optional[str]) -> Optional[str]:
        """Canonical spelling for an exact (normalized) match or a known alias, else None.
        This is what makes 'utility', 'Utility ' and 'UTILITY' all land on 'Utility'."""
        key = normalize(candidate)
        if not key:
            return None
        if key in {normalize(k) for k in ALIASES}:
            target = next(v for k, v in ALIASES.items() if normalize(k) == key)
            key = normalize(target)
        row = self.db.execute("SELECT name FROM industries WHERE norm=?", (key,)).fetchone()
        return row[0] if row else None

    def near_matches(self, candidate: str, threshold: float = 0.70) -> list[str]:
        """Existing markets suspiciously close to `candidate` (e.g. 'Utilities' vs 'Utility').
        Used to refuse an accidental near-duplicate before it forks the vocabulary.

        0.70 is chosen from measured data, not taste: real variants of the seeded markets
        ('Utilities'/'Utility' = 0.75, 'Semiconductors'/'Semiconductor' = 0.96) all sit at or
        above 0.75, while the two most-similar DISTINCT seeded markets only reach 0.44. The
        threshold sits in that gap, so plurals/typos are caught and real markets are not.
        """
        key = normalize(candidate)
        out = []
        for name in self.all():
            n = normalize(name)
            if n == key:
                continue
            if similarity(candidate, name) >= threshold or key in n or n in key:
                out.append(name)
        return out

    def add(self, name: str, force: bool = False) -> str:
        """Register a genuinely new market. Returns the canonical name.

        Refuses (ValueError) when the name collides with, or is suspiciously close to, an
        existing market -- unless `force` says the operator really means it."""
        name = (name or "").strip()
        if not name:
            raise ValueError("market name cannot be empty")
        existing = self.resolve(name)
        if existing:
            return existing                      # already known; reuse canonical spelling
        near = self.near_matches(name)
        if near and not force:
            raise ValueError(
                f"'{name}' looks like an existing market ({', '.join(near)}). "
                f"Use the existing one, or pass force=True if it is genuinely different.")
        self.db.execute("INSERT INTO industries (name, norm) VALUES (?,?)", (name, normalize(name)))
        self.db.commit()
        return name
