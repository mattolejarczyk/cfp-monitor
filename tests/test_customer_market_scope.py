"""The weekly digest and invariant 8 speak only for the two customer markets (2026-10-18).

The database still holds six prospect markets that nobody researches or pays for. Their
dead links and name-year drift are not the customer's, so they must not reach the digest.
"""
import csv
from pathlib import Path

from scripts.check_invariants import CUSTOMER_MARKETS, delivered_ids


def _seed(path: Path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT_ID_CANON", "Market"])
        w.writerows(rows)


def test_customer_markets_are_exactly_the_two():
    assert set(CUSTOMER_MARKETS) == {"Cybersecurity", "Utility"}


def test_delivered_ids_filters_to_the_given_markets(tmp_path):
    _seed(tmp_path / "cyber_seed.csv", [("2026-a", "Cybersecurity")])
    _seed(tmp_path / "utility_seed.csv", [("2026-b", "Utility")])
    _seed(tmp_path / "semi_seed.csv", [("2026-c", "Semiconductor")])
    everything, _ = delivered_ids(tmp_path)
    scoped, _ = delivered_ids(tmp_path, CUSTOMER_MARKETS)
    assert everything == {"2026-a", "2026-b", "2026-c"}
    assert scoped == {"2026-a", "2026-b"}
