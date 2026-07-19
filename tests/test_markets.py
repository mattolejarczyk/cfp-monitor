"""Offline tests for the market registry + list-filename parsing.

Two guarantees under test: the vocabulary cannot silently fragment (Utility/Utilities/
utility), and a filename we can't confidently match is left blank rather than guessed.
"""
import sqlite3

from cfp_monitor.markets import (
    DEFAULT_MARKETS, MarketRegistry, normalize, parse_filename,
)


def _reg(seed=None):
    return MarketRegistry(sqlite3.connect(":memory:"), seed=seed)


# ---- filename parsing (against the customer's REAL filenames) --------------
def test_parses_the_real_customer_filenames():
    cases = {
        "Additive_Manufacturing_3D_Printing_Conference_List_2026.xlsx":
            ("Additive Manufacturing 3D Printing", "Conferences"),
        "Bioeconomy_Biofuels_Conference_List_2026.xlsx": ("Bioeconomy Biofuels", "Conferences"),
        "Biotech_MedTech_Conference_List_2026.xlsx": ("Biotech MedTech", "Conferences"),
        "Consumer_Electronics_Conference_List_2026.xlsx": ("Consumer Electronics", "Conferences"),
        "Robotics_Industry_Conference_List_2026.xlsx": ("Robotics", "Conferences"),
        "Semiconductor_Industry_Conference_List_2026.xlsx": ("Semiconductor", "Conferences"),
        "Utility Global Conference List 2026.xlsx": ("Utility", "Conferences"),
        "Utility Global Award List 2026.xlsx": ("Utility", "Awards"),
        "Arnica Awards 2026.xlsx": ("Arnica", "Awards"),
        "Arnica Conferences 2026.xlsx": ("Arnica", "Conferences"),
    }
    for filename, expected in cases.items():
        assert parse_filename(filename) == expected, filename


def test_all_real_filenames_resolve_to_a_seeded_market():
    reg = _reg()
    for filename in [
        "Additive_Manufacturing_3D_Printing_Conference_List_2026.xlsx",
        "Bioeconomy_Biofuels_Conference_List_2026.xlsx",
        "Biotech_MedTech_Conference_List_2026.xlsx",
        "Consumer_Electronics_Conference_List_2026.xlsx",
        "Robotics_Industry_Conference_List_2026.xlsx",
        "Semiconductor_Industry_Conference_List_2026.xlsx",
        "Utility Global Conference List 2026.xlsx",
        "Utility Global Award List 2026.xlsx",
        "Arnica Awards 2026.xlsx",
    ]:
        candidate, _ = parse_filename(filename)
        assert reg.resolve(candidate) is not None, filename


def test_download_suffix_and_year_are_stripped():
    assert parse_filename("utility_cfp_customer (3).csv")[0] == "utility"


def test_unmatched_filename_yields_no_market_never_guesses():
    reg = _reg()
    candidate, _ = parse_filename("Q3 partner deck FINAL.xlsx")
    assert reg.resolve(candidate) is None


# ---- controlled vocabulary ------------------------------------------------
def test_case_and_separator_variants_resolve_to_one_canonical_name():
    reg = _reg()
    for variant in ("utility", "UTILITY", " Utility ", "utility"):
        assert reg.resolve(variant) == "Utility"
    assert reg.resolve("biotech medtech") == "Biotech & MedTech"
    assert reg.resolve("Biotech_MedTech") == "Biotech & MedTech"


def test_adding_an_existing_market_reuses_canonical_spelling():
    reg = _reg()
    assert reg.add("utility") == "Utility"
    assert len(reg.all()) == len(DEFAULT_MARKETS)      # no duplicate created


def test_near_duplicate_is_refused_unless_forced():
    reg = _reg()
    try:
        reg.add("Utilities")
    except ValueError as e:
        assert "Utility" in str(e)
    else:
        raise AssertionError("near-duplicate 'Utilities' should have been refused")
    # ...but an operator who means it can override
    assert reg.add("Utilities", force=True) == "Utilities"


def test_common_variants_of_every_seeded_market_are_refused():
    """Plurals/typos of any seeded market must never create a second entry."""
    reg = _reg()
    for base, variant in [("Utility", "Utilities"), ("Robotics", "Roboticss"),
                          ("Semiconductor", "Semiconductors"),
                          ("Consumer Electronics", "Consumer Electronic")]:
        try:
            reg.add(variant)
        except ValueError as e:
            assert base in str(e), (variant, str(e))
        else:
            raise AssertionError(f"{variant!r} should have been refused as near-{base!r}")


def test_distinct_seeded_markets_are_not_near_duplicates_of_each_other():
    """Guards the threshold: adding a new seed market must not collide with an existing one."""
    reg = _reg()
    for m in DEFAULT_MARKETS:
        others = [n for n in reg.near_matches(m) if n != m]
        assert others == [], f"{m!r} collides with {others!r} — threshold too loose"


def test_genuinely_new_market_is_accepted():
    reg = _reg()
    assert reg.add("Maritime Logistics") == "Maritime Logistics"
    assert "Maritime Logistics" in reg.all()


def test_empty_market_rejected():
    reg = _reg()
    for bad in ("", "   ", None):
        try:
            reg.add(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad!r}")


def test_normalize_collapses_punctuation_and_case():
    assert normalize("Biotech & MedTech") == normalize("biotech_medtech") == "biotechmedtech"
