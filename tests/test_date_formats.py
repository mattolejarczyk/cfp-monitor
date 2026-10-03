"""Recall limiter 2 (2026-10-03): dates written the German, French, Spanish, Italian or numeric way, ordinals, and ranges. Every form still carries the YEAR and the digit boundaries,
so a date of another year, or a longer number, can never match."""
from datetime import date

import pytest

from scripts.start_date_arbiter import expand_ranges
from src.cfp_monitor.verify import find_date


@pytest.mark.parametrize("text,d", [
    ("Sa, 23.09.2026 in Karlsruhe", date(2026, 9, 23)),
    ("23. September 2026", date(2026, 9, 23)),
    ("am 23.–24. September 2026", date(2026, 9, 23)),
    ("am 23.–24. September 2026", date(2026, 9, 24)),
    ("23.-24.09.2026", date(2026, 9, 23)),
    ("23.-24.09.2026", date(2026, 9, 24)),
    ("10 de mayo de 2027", date(2027, 5, 10)),
    ("du 10 au 12 mars 2027", date(2027, 3, 10)),
    ("du 10 au 12 mars 2027", date(2027, 3, 12)),
    ("1er mars 2027", date(2027, 3, 1)),
    ("März 2027: 8. März 2027", date(2027, 3, 8)),
    ("il 5 settembre 2026", date(2026, 9, 5)),
    ("May 10-12th, 2027", date(2027, 5, 10)),
    ("26 - 27 January 2027", date(2027, 1, 26)),
    ("June 8-10, 2027", date(2027, 6, 8)),
    ("October 27 – 29, 2026", date(2026, 10, 27)),
])
def test_forms_that_must_match(text, d):
    assert find_date(expand_ranges(text), d)


@pytest.mark.parametrize("text,d", [
    ("23.09.2025", date(2026, 9, 23)),                 # another year
    ("am 23.–24. September 2025", date(2026, 9, 23)),
    ("123.09.2026", date(2026, 9, 23)),                # a longer number
    ("12.10.2026", date(2026, 10, 2)),                 # 12 is not 2
    ("10 mayo 2026", date(2027, 5, 10)),
    ("Join us 2026 - 23 October 2026", date(2026, 10, 2)),   # an expanded year must never be re-read as a day
])
def test_forms_that_must_not_match(text, d):
    assert not find_date(expand_ranges(text), d)
