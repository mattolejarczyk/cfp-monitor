"""The v1.5 columns must survive the import.

Upstream ships the first 43-column delivery on 2026-08-26. Without this, the file passes the
acceptance gate and the five new fields are then silently discarded - upstream does the work, we
accept the file, the data evaporates, and nothing reports it. A column the importer does not
know about is not missing, it is simply never read.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.grounding import _COL, normalize_rows  # noqa: E402
from src.cfp_monitor.storage import Store  # noqa: E402


def raw(**over):
    r = {"CONFERENCE": "Test Conf 2027", "CONFERENCE URL": "https://ex.com",
         "Market": "Utility", "EDITION": "2027", "CITY": "Austin", "STATE_PROVINCE": "TX",
         "COUNTRY": "USA", "LOCATION": "Austin, TX, USA", "SUBMISSION DEADLINE": "2027-01-01",
         "SUBMISSION URL": "", "CFP MODEL TYPE": "Fixed Deadline", "STATUS": "Open",
         "OVERVIEW": "", "CATEGORIES": "", "COORDINATOR EMAIL": "", "DEADLINE_QUOTE": "",
         "IS_PROJECTED": "false", "SOURCE_AS_OF": "", "DEADLINE_EVIDENCE_URL": "",
         "MAIN_INFO_URL": "", "OPPORTUNITY_TYPE": "Speaking"}
    r.update(over)
    return r


# --------------------------------------------------------------- the mapping --
def test_all_five_v15_columns_are_mapped():
    """If a name here drifts from the delivery header, the value is dropped in silence."""
    for col in ("ORGANIZER", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST",
                "SPONSOR_QUOTE"):
        assert col in _COL.values(), f"{col} is not mapped - it would be discarded on import"


def test_the_values_reach_the_row(tmp_path):
    rows, _ = normalize_rows([raw(**{"ORGANIZER": "Reuters Events",
                                     "SPONSOR_REQUIRED": "Yes",
                                     "SPONSOR_URL": "https://ex.com/sponsor",
                                     "SPONSOR_COST": "Gold $25,000"})])
    r = rows[0]
    assert r.organizer == "Reuters Events"
    assert r.sponsor_required == "Yes"
    assert r.sponsor_url == "https://ex.com/sponsor"
    assert r.sponsor_cost == "Gold $25,000"


def test_a_pre_v15_delivery_still_imports(tmp_path):
    """A 38-column file has none of these. It must construct cleanly, not raise."""
    rows, _ = normalize_rows([raw()])
    assert rows[0].organizer == ""
    assert rows[0].sponsor_url == ""


def test_a_missing_sponsor_required_defaults_to_Unknown():
    """R18.1 - never blank, never No."""
    assert normalize_rows([raw()])[0][0].sponsor_required == "Unknown"
    assert normalize_rows([raw(**{"SPONSOR_REQUIRED": ""})])[0][0].sponsor_required == "Unknown"


def test_an_explicit_value_is_not_overridden_by_the_default():
    assert normalize_rows([raw(**{"SPONSOR_REQUIRED": "No"})])[0][0].sponsor_required == "No"


# ------------------------------------------------------------- the database --
def test_the_columns_exist_on_a_fresh_database(tmp_path):
    Store(str(tmp_path / "new.db")).close() if hasattr(Store, "close") else Store(
        str(tmp_path / "new.db"))
    cols = {r[1] for r in sqlite3.connect(tmp_path / "new.db").execute(
        "pragma table_info(grounding_facts)")}
    for c in ("organizer", "sponsor_required", "sponsor_url", "sponsor_cost", "sponsor_quote"):
        assert c in cols, f"{c} missing from a freshly created database"


def test_an_old_database_is_migrated_not_broken(tmp_path):
    """A database created before v1.5 must gain the columns, not fail to open."""
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE grounding_facts (event_id TEXT PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO grounding_facts VALUES ('e1','Existing Row')")
    con.commit()
    con.close()

    Store(str(p))                                   # opening runs the migration

    con = sqlite3.connect(p)
    cols = {r[1] for r in con.execute("pragma table_info(grounding_facts)")}
    for c in ("organizer", "sponsor_required", "sponsor_url", "sponsor_cost", "sponsor_quote"):
        assert c in cols
    kept = con.execute("select name from grounding_facts where event_id='e1'").fetchone()
    assert kept and kept[0] == "Existing Row", "migration lost an existing row"
