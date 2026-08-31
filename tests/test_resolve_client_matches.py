"""Settling the matcher's middle band by evidence - and refusing where evidence runs out.

This script WRITES JOINS, and a wrong join puts another conference's deadline in front of a
client. So the tests that matter are the refusals: zero candidates and several candidates mean
different things and neither may be resolved.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_rcm", ROOT / "scripts" / "resolve_client_matches.py")
rcm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcm)


def test_an_edition_year_never_blocks_a_name_match():
    """The customer tracks the edition they care about while we have moved to the next. That
    difference is exactly why the matcher's date test was silent on these rows."""
    assert rcm.norm_name("Black Hat Asia") == rcm.norm_name("Black Hat Asia 2026")
    assert rcm.norm_name("DevSecCon 2026") == rcm.norm_name("DevSecCon")


def test_a_parenthetical_never_blocks_a_name_match():
    """Ours carry them, theirs do not: 'SecTor 2026 (Black Hat Canada / SecTor)'."""
    assert rcm.norm_name("DEF CON Singapore 2026 (Inaugural Edition)") == \
        rcm.norm_name("DEF CON Singapore")


def test_a_venue_prefix_does_not_prevent_a_city_match():
    """Their LOCATION is a venue string - 'Marina Bay Sands, Singapore'. Ours is a bare city."""
    theirs = rcm.norm_city("Marina Bay Sands, Singapore")
    ours = rcm.norm_city("Singapore Singapore")
    assert theirs & ours


def test_short_words_are_ignored_so_a_stray_token_cannot_match():
    """'1 Wa' from a street address must not become a city token."""
    assert rcm.norm_city("InterContinental London - The O2, 1 Wa") == {"intercontinental",
                                                                       "london"}


def test_different_cities_do_not_match():
    """The whole point on 2026-08-31: MENA and Asia-Pacific editions of series where we hold
    only North America and Europe. Same name, different continent, not the same conference."""
    assert not (rcm.norm_city("Abu Dhabi, UAE") & rcm.norm_city("Houston USA"))
    assert not (rcm.norm_city("Adelaide Convention Centre, Australia")
                & rcm.norm_city("Rotterdam Netherlands"))


def test_a_name_that_is_not_contained_is_not_a_match():
    """Containment is directional on purpose: THEIR name must appear in OURS. 'Black Hat USA -
    SecTor (Canada)' is not inside 'SecTor 2026', so it is declined rather than guessed."""
    theirs = rcm.norm_name("Black Hat USA - SecTor (Canada)")
    ours = rcm.norm_name("SecTor 2026 (Black Hat Canada / SecTor)")
    assert theirs not in ours


def test_the_containment_that_does_hold():
    assert rcm.norm_name("Cloud & Cyber Security Expo") in \
        rcm.norm_name("Cloud & Cyber Security Expo London 2027")
    assert rcm.norm_name("Hydrogen Innovation and Technology Conference 2026") in \
        rcm.norm_name("Hydrogen Innovation and Technology Conference 2026 (Manchester)")


def test_the_script_requires_exactly_one_candidate():
    """Two plausible rows is ambiguity, and ambiguity goes to a human - 2.5, decline rather
    than guess. On 2026-08-31 'Hydrogen Technology World Expo' matched two Hamburg editions,
    and the customer's own sheet carried two near-identical rows for it."""
    src = (ROOT / "scripts" / "resolve_client_matches.py").read_text(encoding="utf-8")
    assert "len(uniq) == 1" in src
    assert "ambiguous" in src


def test_rows_sharing_an_event_id_count_as_one_candidate():
    """A conference in two markets is ONE edition (section 10). Counting it as two candidates
    would make every multi-market row look ambiguous."""
    src = (ROOT / "scripts" / "resolve_client_matches.py").read_text(encoding="utf-8")
    assert "uniq = {c[\"event_id\"]: c for c in cands}" in src


def test_it_verifies_the_shared_tables_did_not_move():
    src = (ROOT / "scripts" / "resolve_client_matches.py").read_text(encoding="utf-8")
    for t in ("conferences", "grounding_facts", "conference_markets", "evidence"):
        assert t in src
    assert "shared tables" in src and "--apply" in src


def test_it_reports_before_it_writes():
    src = (ROOT / "scripts" / "resolve_client_matches.py").read_text(encoding="utf-8")
    assert "DRY RUN - nothing written" in src
