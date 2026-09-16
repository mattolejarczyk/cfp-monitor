"""A lifecycle claim survives the import - and a blank cell can never erase one.

R16 (v1.3) put LIFECYCLE_EVIDENCE_URL and LIFECYCLE_QUOTE in the delivery. The gate checks them and
the customer page renders them, but until 2026-09-16 `grounding_facts` had no column for either, so
import read them and dropped them. Found through a duplicate that was not one: we held a projected
ShmooCon 2027 for a series that ended in January 2025, and upstream had already told us so.

These go through `seed_store` against a real database, not the row object, because the
dangerous part is the ON CONFLICT clause - and the research prompt has never requested these
fields, so upstream ships them BLANK on almost every row, almost every cycle. A plain
`excluded.lifecycle_quote` would clear a discontinuation on the next weekly import, silently.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.grounding import _COL, normalize_rows, seed_store  # noqa: E402
from src.cfp_monitor.storage import Store                             # noqa: E402

PAGE = "https://en.wikipedia.org/wiki/ShmooCon"
QUOTE = "The first event was held in 2005, with its last year was in 2025."


def raw(**over):
    r = {"CONFERENCE": "ShmooCon 2027", "CONFERENCE URL": "https://shmoocon.org/",
         "Market": "Cybersecurity", "EDITION": "2027", "CITY": "Washington",
         "STATE_PROVINCE": "D.C.", "COUNTRY": "USA", "LOCATION": "Washington, D.C., USA",
         "SUBMISSION DEADLINE": "", "SUBMISSION URL": "", "CFP MODEL TYPE": "Not Announced",
         "STATUS": "Closed", "OVERVIEW": "", "CATEGORIES": "", "COORDINATOR EMAIL": "",
         "DEADLINE_QUOTE": "", "IS_PROJECTED": "true", "SOURCE_AS_OF": "2026-09-12",
         "DEADLINE_EVIDENCE_URL": "", "MAIN_INFO_URL": "", "OPPORTUNITY_TYPE": "Speaking",
         "LIFECYCLE_EVIDENCE_URL": "", "LIFECYCLE_QUOTE": ""}
    r.update(over)
    return r


def _import(db, **over):
    rows, _ = normalize_rows([raw(**over)])
    store = Store(str(db))
    seed_store(store, rows)
    store.db.commit()
    got = store.db.execute("select event_id, lifecycle_evidence_url, lifecycle_quote"
                           " from grounding_facts").fetchall()
    store.db.close()
    assert len(got) == 1, got
    return got[0][1] or "", got[0][2] or ""


def test_both_columns_are_mapped_from_the_delivery_header():
    """If a name here drifts from the header, the value is dropped in silence - the original bug."""
    for col in ("LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE"):
        assert col in _COL.values(), f"{col} is not mapped - it would be discarded on import"


def test_a_claim_in_the_delivery_reaches_the_database(tmp_path):
    assert _import(tmp_path / "t.db", LIFECYCLE_EVIDENCE_URL=PAGE,
                   LIFECYCLE_QUOTE=QUOTE) == (PAGE, QUOTE)


def test_a_blank_reimport_never_erases_a_claim(tmp_path):
    """THE ONE THAT MATTERS. Next Saturday's delivery will almost certainly carry these blank,
    because nothing asks upstream's model for them. That must not clear the only record that the
    event is over."""
    db = tmp_path / "t.db"
    _import(db, LIFECYCLE_EVIDENCE_URL=PAGE, LIFECYCLE_QUOTE=QUOTE)
    assert _import(db) == (PAGE, QUOTE)


def test_a_new_claim_replaces_the_old_one_as_a_pair(tmp_path):
    """URL and quote are one claim. A new quote beside the old page would be a split citation, in
    the one field R16.2 puts beyond R1's reach to correct."""
    db = tmp_path / "t.db"
    _import(db, LIFECYCLE_EVIDENCE_URL=PAGE, LIFECYCLE_QUOTE=QUOTE)
    new_page, new_quote = "https://shmoocon.org/final", "ShmooCon XX was the last."
    assert _import(db, LIFECYCLE_EVIDENCE_URL=new_page,
                   LIFECYCLE_QUOTE=new_quote) == (new_page, new_quote)


def test_a_page_without_a_quote_does_not_displace_a_whole_claim(tmp_path):
    """Half a claim never overwrites a whole one. The gate is what rejects the half; the import
    must not quietly trade a quoted claim for an unquoted link."""
    db = tmp_path / "t.db"
    _import(db, LIFECYCLE_EVIDENCE_URL=PAGE, LIFECYCLE_QUOTE=QUOTE)
    assert _import(db, LIFECYCLE_EVIDENCE_URL="https://elsewhere.example/") == (PAGE, QUOTE)


def test_a_row_that_never_had_a_claim_stays_empty(tmp_path):
    """The inversion: GOOD input survives. Most rows carry nothing, and must still carry nothing."""
    db = tmp_path / "t.db"
    _import(db)
    assert _import(db) == ("", "")


def test_an_old_database_gains_the_columns(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE grounding_facts (event_id TEXT PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO grounding_facts VALUES ('e1','Existing Row')")
    con.commit()
    con.close()
    Store(str(p)).db.close()                        # opening runs the migration
    con = sqlite3.connect(p)
    cols = {r[1] for r in con.execute("pragma table_info(grounding_facts)")}
    assert {"lifecycle_evidence_url", "lifecycle_quote"} <= cols
    assert con.execute("select name from grounding_facts").fetchone()[0] == "Existing Row"
