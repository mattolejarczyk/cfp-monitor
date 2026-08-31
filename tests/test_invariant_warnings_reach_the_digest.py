"""An integrity warning must reach the person, not just the log.

`check_invariants.py` printed "edition matches the name year - run fix_edition.py (71)" on every
Sunday run from 2026-08-12. It exits 0 for a warning, so the digest only ever showed invariants
when they FAILED, and the line went to runs_out/weekly_*.log where nobody reads it.

Nineteen days later 67 rows still carried an edition stamped with the year the research ran
instead of the year the conference happens - and because event_id is built from the edition, two
of them had become duplicate rows for the same conference.

Detection was never the gap. A warning with no owner and no due date is furniture.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_wv", ROOT / "scripts" / "weekly_verify.py")
wv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wv)

TODAY = date(2026, 8, 31)

# Verbatim from a real run.
REAL = """Invariants - cfp_monitor.db
  392 DB row(s) | 391 delivered id(s) across 9 seed file(s) | 1 declared hold(s)

  [ok  ] 1  no delivered row is missing     every EVENT_ID_CANON in a seed exists in the DB
  [ok  ] 5  event_id is unique              one row per canonical id
  [ok  ] 7  keys never moved                event_id still carries the year it was minted with
  [warn] 8  edition matches the name year   watch: run fix_edition.py to derive from date  (5)
            - CE Week 2027 - edition 2026, name says 2027

RESULT: all invariants hold (1 watch item(s) - not failures)
"""


def test_a_warning_is_pulled_out_of_the_invariant_output():
    got = wv.parse_invariant_warnings(REAL)
    assert len(got) == 1
    label, hint = got[0]
    assert "edition matches the name year" in label
    assert "5 row(s)" in label, "the count is the size of the problem and must survive"
    assert "fix_edition.py" in hint, "the tool that fixes it must survive"


def test_passing_checks_are_not_reported_as_warnings():
    """[ok] lines outnumber [warn] lines seven to one. Treating them alike would bury it."""
    assert all("edition" in lab for lab, _ in wv.parse_invariant_warnings(REAL))
    assert len(wv.parse_invariant_warnings(REAL)) == 1


def test_a_clean_run_produces_nothing():
    clean = "  [ok  ] 1  no delivered row is missing   every id exists\nRESULT: all hold\n"
    assert wv.parse_invariant_warnings(clean) == []
    assert wv.parse_invariant_warnings("") == []


def test_a_warning_with_no_count_still_survives():
    line = "  [warn] 3  something is drifting   watch: run some_tool.py to fix it\n"
    got = wv.parse_invariant_warnings(line)
    assert len(got) == 1 and "some_tool.py" in got[0][1]


def _digest(warnings):
    return wv.build_digest({}, {}, {}, TODAY, still_cited=set(),
                           invariant_warnings=warnings)[0]


def test_the_warning_reaches_the_digest_with_an_owner_and_a_deadline():
    """The whole point. It reached the LOG for nineteen days and nobody acted."""
    out = _digest(wv.parse_invariant_warnings(REAL))
    assert "## Database watch items (1)" in out
    assert "fix_edition.py" in out
    assert "cfp-monitor (us)" in out
    assert "This week." in out


def test_it_appears_in_the_at_a_glance_table_as_work():
    out = _digest(wv.parse_invariant_warnings(REAL))
    assert "## At a glance" in out
    assert "Database watch items" in out.split("## Database watch items")[0], \
        "it must be in the summary table, not only in its own section"
    assert "**1 row(s) need someone to act.**" in out


def test_the_section_says_re_running_will_not_help():
    """These do not resolve on their own, and a reader who assumes the next sweep clears them
    will keep skipping the line - which is exactly what happened."""
    out = _digest(wv.parse_invariant_warnings(REAL))
    assert "do not resolve on their own" in out
    assert "no amount of re-verifying moves them" in out


def test_a_week_with_no_warnings_stays_quiet():
    out = _digest([])
    assert "Database watch items" not in out
    assert "Nothing changed and nothing is outstanding" in out
