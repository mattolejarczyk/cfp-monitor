"""Merging two records of one event: who survives, and what the merge must never do.

The expensive mistake is not a bad merge of facts. It is deleting the row the CUSTOMER is
joined to, because their status, priority and notes hang off that key and nothing in our
evidence tells us it mattered.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("mde",
                                               ROOT / "scripts" / "merge_duplicate_events.py")
mde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mde)

from src.cfp_monitor.clients import ensure_schema      # noqa: E402
from src.cfp_monitor.storage import Store              # noqa: E402


def _row(event_id, **kw):
    r = {"event_id": event_id, "name": "Big Conference 2027", "city": "Houston",
         "edition": "2027", "deadline": "", "deadline_quote": "", "deadline_evidence_url": "", "is_projected": "false",
         "verify_state": "not_found", "source_as_of": "2026-09-12", "submission_url": ""}
    r.update(kw)
    return r


def _rows(tmp_path, rows, clients=()):
    p = tmp_path / "t.db"
    Store(str(p)).db.close()
    con = sqlite3.connect(str(p))
    ensure_schema(con)                       # the client layer is its own migration
    for r in rows:
        con.execute(f"insert into grounding_facts ({', '.join(r)})"
                    f" values ({', '.join('?' for _ in r)})", list(r.values()))
    for c in clients:
        con.execute("insert into client_conferences (client_key, their_name, event_id, status)"
                    " values (?, ?, ?, ?)", (c[0], "Their Name", c[1], c[2]))
    con.commit()
    con.row_factory = sqlite3.Row
    got = list(con.execute("select * from grounding_facts"))
    linked = {r["event_id"]: dict(r) for r in con.execute("select * from client_conferences")}
    con.close()
    return got, linked


OLD = "2026-big-conference-houston"
NEW = "2027-big-conference-houston"


def test_the_row_the_customer_is_joined_to_survives_even_when_it_is_older(tmp_path):
    """Six of the seven live groups on 2026-09-14 were exactly this shape. A keep-the-newest
    merge would have orphaned Nicolia's matches, two of them rows they were actively working."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07"),
                          _row(NEW, verify_state="verified", deadline="2026-10-19")],
                         clients=[("utility-global", OLD, "Drafting Abstract")])
    p = mde.plan_one(rows, linked)
    assert p["keep"]["event_id"] == OLD
    assert [x["event_id"] for x in p["losers"]] == [NEW]


def test_the_newer_rows_facts_move_onto_the_survivor(tmp_path):
    """The survivor keeps its key and its customer join; it does not keep its stale evidence."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07"),
                          _row(NEW, verify_state="verified", deadline="2026-10-19",
                               deadline_quote="Regular closes 19 October")],
                         clients=[("utility-global", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert ch["deadline"][1] == "2026-10-19"
    assert ch["verify_state"][1] == "verified"


def test_a_blank_never_overwrites_a_populated_field(tmp_path):
    """The merge guard apply_resolutions.py --citations already uses. Without it the newer row
    silently empties everything it did not happen to re-find."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07", deadline="2026-10-19",
                               submission_url="https://a.test/cfp"),
                          _row(NEW, deadline="", submission_url="")],
                         clients=[("utility-global", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert "deadline" not in ch and "submission_url" not in ch


def test_an_older_populated_field_does_not_beat_a_newer_one(tmp_path):
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07", deadline="2026-12-20"),
                          _row(NEW, source_as_of="2026-09-12", deadline="2026-10-19")],
                         clients=[("utility-global", OLD, "")])
    assert mde.plan_one(rows, linked)["changes"]["deadline"][1] == "2026-10-19"


def test_two_customer_links_block_the_merge_rather_than_picking_one(tmp_path):
    """Deleting either row breaks a join the customer relies on. That is a decision, not a
    default - and a silent default here is unrecoverable."""
    rows, linked = _rows(tmp_path, [_row(OLD), _row(NEW)],
                         clients=[("utility-global", OLD, ""), ("arnica", NEW, "")])
    p = mde.plan_one(rows, linked)
    assert "AMBIGUOUS" in p["error"]
    assert "keep" not in p


def test_with_no_customer_link_the_better_evidenced_row_survives(tmp_path):
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07"),
                          _row(NEW, verify_state="verified", deadline="2026-10-19",
                               deadline_quote="q", deadline_evidence_url="https://a.test")])
    assert mde.plan_one(rows, linked)["keep"]["event_id"] == NEW


def test_the_customers_own_columns_are_never_in_the_merge(tmp_path):
    """Contract 3. STATUS, NOTES and PRIORITY on client_conferences are theirs; the survivor is
    chosen the way it is precisely so none of them ever has to be rewritten."""
    assert "notes" not in mde.FACT_FIELDS
    assert "priority" not in mde.FACT_FIELDS
    assert all(t != "client_conferences" for t, _ in mde.ATTACHED)


REG = "2027-big-conference-houston-registration"


def test_a_registration_row_never_supplies_submission_facts(tmp_path):
    """The draft caught itself on 2026-09-14: merging SIEW's registration row would have moved
    'Registration is now open for the 1...' onto the speaking row as its deadline quote. That is
    the CES stale-crawl mistake exactly - an open ticket desk read as an open call."""
    rows, linked = _rows(tmp_path,
                         [_row(NEW, source_as_of="2026-08-07"),
                          _row(REG, deadline="2026-10-19",
                               deadline_quote="Registration is now open for the 18th edition",
                               submission_url="https://siew.test/", verify_state="verified")],
                         clients=[("utility-global", NEW, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert "deadline" not in ch and "deadline_quote" not in ch
    assert "submission_url" not in ch and "verify_state" not in ch


def test_a_registration_row_may_still_describe_the_event(tmp_path):
    """It cannot date an abstract; it can still say who runs the event. Discarding the whole row
    would throw away good information to avoid bad."""
    rows, linked = _rows(tmp_path,
                         [_row(NEW, source_as_of="2026-08-07"),
                          _row(REG, organizer="Energy Market Authority")],
                         clients=[("utility-global", NEW, "")])
    assert mde.plan_one(rows, linked)["changes"]["organizer"][1] == "Energy Market Authority"


def test_a_speaking_row_still_supplies_submission_facts(tmp_path):
    """The inversion: the guard must not quietly block a legitimate merge."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07"),
                          _row(NEW, deadline="2026-10-19", verify_state="verified")],
                         clients=[("utility-global", OLD, "")])
    assert mde.plan_one(rows, linked)["changes"]["deadline"][1] == "2026-10-19"


def test_is_projected_cannot_travel_without_its_citation(tmp_path):
    """R2/R11. Caught on ACT Expo 2026-09-14: the newer row carried is_projected=true with no
    quote and no evidence URL, while the survivor held a verified deadline quote. Moving the
    flag alone relabels an evidenced deadline a projection."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07", deadline="2026-09-10",
                               deadline_quote="Submissions Deadline: Friday, September 10, 2026",
                               is_projected="false"),
                          _row(NEW, deadline="", deadline_quote="", is_projected="true")],
                         clients=[("utility-global", OLD, "")])
    assert "is_projected" not in mde.plan_one(rows, linked)["changes"]


def test_is_projected_travels_when_the_citation_does(tmp_path):
    """The inversion: the guard must not strand a flag that belongs with a date we did take."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07", is_projected="false"),
                          _row(NEW, deadline="2026-09-30", is_projected="true")],
                         clients=[("utility-global", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert ch["deadline"][1] == "2026-09-30" and ch["is_projected"][1] == "true"


def test_seeds_are_repointed_at_the_survivor(tmp_path):
    """THE STEP THE MERGE IS NOT DONE WITHOUT. identity.seed_map reads EVENT_ID_CANON straight
    out of these files, so a seed still naming a deleted key makes the next import insert it
    again - the duplicate returns every Saturday. check_invariants caught this live on
    2026-09-14, which is what a reconciliation after a mutation is for."""
    import csv as _csv
    seeds = tmp_path / "market_sheets"
    seeds.mkdir()
    f = seeds / "utility_seed.csv"
    with open(f, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["EVENT_ID", "EVENT_ID_CANON", "NAME"])
        w.writeheader()
        w.writerow({"EVENT_ID": "theirs-1", "EVENT_ID_CANON": NEW, "NAME": "Big"})
        w.writerow({"EVENT_ID": "theirs-2", "EVENT_ID_CANON": "untouched", "NAME": "Other"})
    (tmp_path / "t.db").touch()
    out = mde.repoint_seeds(str(tmp_path / "t.db"), {NEW: OLD})
    assert out and "1 row(s)" in out[0]
    got = {r["EVENT_ID"]: r["EVENT_ID_CANON"]
           for r in _csv.DictReader(open(f, encoding="utf-8-sig"))}
    assert got == {"theirs-1": OLD, "theirs-2": "untouched"}
    assert list(seeds.glob("*.before-merge-*.csv")), "the original must be kept"


def test_a_deadline_never_arrives_without_the_verdict_that_judged_it(tmp_path):
    """SecureWorld St. Louis, 2026-09-14. The survivor's deadline was blank so it would have
    taken 2026-07-08 off a CONTRADICTED row, kept its own not_found, and gained neither quote
    nor URL - a disputed date arriving stripped of the dispute."""
    rows, linked = _rows(tmp_path,
                         [_row(NEW, deadline="", verify_state="not_found"),
                          _row(OLD, source_as_of="2026-08-05", deadline="2026-07-08",
                               verify_state="contradicted")],
                         clients=[("utility-global", NEW, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    if "deadline" in ch:                       # if the date moves, the verdict moves with it
        assert ch["verify_state"][1] == "contradicted"


def test_the_whole_citation_cluster_moves_from_one_row(tmp_path):
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07"),
                          _row(NEW, deadline="2026-10-19", deadline_quote="Closes 19 October",
                               deadline_evidence_url="https://a.test/cfp",
                               verify_state="verified")],
                         clients=[("utility-global", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert {c[2] for f, c in ch.items() if f in mde.CITATION_FIELDS} == {NEW}
    assert ch["deadline_quote"][1] == "Closes 19 October"
    assert ch["verify_state"][1] == "verified"


def test_an_evidenced_quote_on_the_survivor_is_not_disturbed(tmp_path):
    """The survivor proved its own date. A merge is not a reason to re-open that."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-07", deadline="2026-09-10",
                               deadline_quote="Submissions Deadline: Friday, September 10, 2026",
                               verify_state="verified"),
                          _row(NEW, deadline="", verify_state="not_found", is_projected="true")],
                         clients=[("utility-global", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert not any(f in ch for f in mde.CITATION_FIELDS)


def test_the_events_own_name_breaks_a_city_tie(tmp_path):
    """SecureWorld St. Louis 2026, held as both St. Louis and Clayton - the venue's town. An
    evidence count preferred Clayton; invariant 3 cannot catch it because Clayton is a real
    place, not a venue string. The name can."""
    rows, linked = _rows(tmp_path,
                         [_row("2026-secureworld-st-louis-clayton", name="SecureWorld St. Louis 2026",
                               city="Clayton", edition="2026", deadline="2026-07-08",
                               deadline_quote="q", verify_state="verified"),
                          _row("2026-secureworld-st-louis-st-louis", name="SecureWorld St. Louis 2026",
                               city="St. Louis", edition="2026", source_as_of="2026-08-05")])
    assert mde.plan_one(rows, linked)["keep"]["city"] == "St. Louis"


def test_a_customer_link_still_outranks_the_name(tmp_path):
    """The name is a TIE-BREAK, not a new top rule. Orphaning a customer join is still worse."""
    rows, linked = _rows(tmp_path,
                         [_row("2026-secureworld-st-louis-clayton", name="SecureWorld St. Louis 2026",
                               city="Clayton", edition="2026"),
                          _row("2026-secureworld-st-louis-st-louis", name="SecureWorld St. Louis 2026",
                               city="St. Louis", edition="2026")],
                         clients=[("arnica", "2026-secureworld-st-louis-clayton", "Submitted")])
    assert mde.plan_one(rows, linked)["keep"]["city"] == "Clayton"


def test_a_name_with_no_city_in_it_falls_back_to_evidence(tmp_path):
    """The inversion: most events are not named for their city, and the old rule must survive."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, city="Houston", source_as_of="2026-08-07"),
                          _row(NEW, city="Boston", deadline="2026-10-19", deadline_quote="q",
                               verify_state="verified")])
    assert mde.plan_one(rows, linked)["keep"]["event_id"] == NEW


def test_a_merge_never_blanks_a_known_deadline(tmp_path):
    """R1, and it outranks the atomicity rule: a citation edit clears the URL and the quote, and
    the submission deadline is never touched. SecureWorld St. Louis, 2026-09-14 - a newer 'this
    event has passed' citation would otherwise have taken a known 2026-07-08 with it."""
    rows, linked = _rows(tmp_path,
                         [_row(OLD, source_as_of="2026-08-05", deadline="2026-07-08",
                               deadline_quote="St. Louis, MO. July 8, 2026.",
                               verify_state="contradicted"),
                          _row(NEW, deadline="", deadline_quote="Thank you for your interest.",
                               verify_state="not_found")],
                         clients=[("arnica", OLD, "")])
    ch = mde.plan_one(rows, linked)["changes"]
    assert ch["deadline_quote"][1] == "Thank you for your interest."   # the citation moves
    assert "deadline" not in ch                                        # the date does not
