"""ACT-22: the awards finder (main-call rule inverted), the live-awards loader and the awards answer-key candidates. Fixture-only: no network, no model."""
import sqlite3

from experiments.finder_reader_test import run as F
from experiments.finder_reader_test.main_call import OTHER, OTHER_AWARD, choose_main, classify
from experiments.read_the_page_pass import key_candidates_awards as K
from scripts.awards_shadow import live_awards

T = "2026-10-05"


def test_the_awards_pattern_does_not_set_aside_awards_nominations_or_entries():
    for word in ("award", "nominat", "prize", "entry", "competition"):
        assert not OTHER_AWARD.search(word), word
    assert OTHER.search("award") and OTHER.search("nominat")                         # the conference rule is unchanged
    for word in ("poster", "workshop", "sponsor", "scholarship", "judging", "notification"):
        assert OTHER_AWARD.search(word), word


def test_a_nomination_page_is_the_main_call_for_an_award_and_an_other_call_for_a_conference():
    c = {"value": "2026-12-01", "url": "https://x.example/awards/nominations", "what": "Nominations close", "quote": "Nominations close on December 1, 2026."}
    assert classify(c, "award") == "main-page" and classify(c) == "other"
    assert choose_main([c], T, "award")["pick"] == "2026-12-01"
    assert choose_main([c], T)["pick"] == ""                                         # conference rule: only an other-call date, honest blank
    conf = {"value": "2026-12-01", "url": "https://x.example/call-for-speakers", "what": "Call for speakers closes", "quote": "Speaker proposals close on December 1, 2026."}
    assert choose_main([conf], T)["pick"] == "2026-12-01" and choose_main([conf], T, "award")["pick"] == "2026-12-01"


def test_awards_still_set_aside_side_calls_and_take_the_earliest_open_round():
    entry = {"value": "2026-11-20", "url": "https://x.example/enter-now", "what": "Entry deadline", "quote": "Entry deadline: November 20, 2026."}
    late = {"value": "2026-12-15", "url": "https://x.example/enter-now", "what": "Late entry deadline", "quote": "Late entry deadline: December 15, 2026."}
    poster = {"value": "2026-10-30", "url": "https://x.example/poster-session", "what": "Poster submission", "quote": "Poster submission closes October 30, 2026."}
    r = choose_main([late, entry, poster], T, "award")
    assert r["pick"] == "2026-11-20" and r["other_calls"] == [("2026-10-30", "https://x.example/poster-session")]


PAGE = "The Example Awards 2027. Entries are open. " + "x " * 200


def test_entry_wording_counts_as_call_wording_for_awards_only():
    item = {"value": "2026-11-20", "quote": "Entries must be received by November 20, 2026"}
    page = PAGE + "Entries must be received by November 20, 2026. " + "x " * 20
    assert F.accept_deadline(item, page, T, "award")[0] == "2026-11-20"
    assert F.accept_deadline(item, page, T)[0] == ""                                  # conference wording has no 'entries'
    assert "ENTER or NOMINATE" in F.AWARDS_SYSTEM and "ENTER or NOMINATE" not in F.SYSTEM


def _db(tmp_path):
    p = tmp_path / "t.db"
    c = sqlite3.connect(p)
    c.execute("create table award_grounding_facts (event_id, name, url, main_info_url, submission_url, deadline_evidence_url, deadline, status, edition, organizer, country)")
    c.execute("create table award_markets (award_key, market)")
    rows = [("a1", "Open Award", "https://a.example/", "", "", "", "2026-12-01", "Open", "2026", "Acme", "Canada"),
            ("a2", "Closed Award", "https://b.example/", "", "", "", "2026-02-01", "Closed", "2026", "", ""),
            ("a3", "Upcoming No Date", "https://c.example/", "", "", "", "", "Upcoming", "2027", "", ""),
            ("a4", "Old Edition", "https://d.example/", "", "", "", "", "Open", "2024", "", ""),
            ("a5", "No Page", "", "", "", "", "2026-12-05", "Open", "2026", "", ""),
            ("a6", "Tracker Only", "https://sessionize.com/x", "", "", "", "2026-12-06", "Open", "2026", "", ""),
            ("a7", "Sooner Award", "https://e.example/", "", "", "", "2026-11-01", "Closed", "2026", "", "")]
    c.executemany("insert into award_grounding_facts values (?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.executemany("insert into award_markets values (?,?)", [("a1", "Cybersecurity"), ("a7", "Utility")])
    c.commit()
    c.close()
    return p


def test_live_awards_are_open_upcoming_or_dated_ahead_with_a_page_soonest_first_read_only(tmp_path):
    db = _db(tmp_path)
    ev = live_awards(db, T, 10)
    assert [e["event"] for e in ev] == ["Sooner Award", "Open Award", "Upcoming No Date"]       # closed-and-past, old edition, no page and tracker-only are out
    assert ev[0]["kind"] == "award" and ev[1]["market"] == "Cybersecurity" and ev[1]["hosts"] == ["a.example"] and ev[1]["organizer"] == "Acme"
    assert len(live_awards(db, T, 1)) == 1
    src = open(live_awards.__code__.co_filename, encoding="utf-8").read()
    assert "mode=ro" in src and "executescript" not in src and " update " not in src.lower()


def test_candidate_lines_say_agree_differs_reader_only_or_unproven():
    ev = {"id": "a1", "event": "Open Award", "market": "Cybersecurity", "ours": "2026-12-01", "organizer": "", "country": "Canada", "edition": "2026"}
    rec = {"pages": [{"rank": 1, "url": "https://a.example/enter", "chars": 3000, "accepted": "2026-12-02", "quote": "Entries close December 2, 2026."}], "pick": {"pick": "2026-12-02", "why": "main-page"}}
    page = "The Example Awards are organised by Acme Events Ltd and held in Canada. Entries close December 2, 2026. " + "x " * 200
    fields = {"organizer": {"value": "Acme Events Ltd", "quote": "organised by Acme Events Ltd"}, "country": {"value": "Canada", "quote": "held in Canada"}}
    rows = K.rows_for(ev, rec, fields, page, {"https://a.example/": page})
    by = {r["field"]: r for r in rows}
    assert by["SUBMISSION DEADLINE"]["status"] == "differs" and by["SUBMISSION DEADLINE"]["tier"].startswith("candidate: DIFFERS")
    assert by["ORGANIZER"]["status"] == "reader-only" and by["COUNTRY"]["status"] == "agree" and by["COUNTRY"]["tier"] == "candidate: page-proven and agrees"
    none = K.rows_for(ev, {"pages": [], "pick": {"pick": "", "why": "no accepted date"}}, {}, "", {})
    assert {r["status"] for r in none} <= {"unproven", "both-blank"} and {r["field"]: r["status"] for r in none}["SUBMISSION DEADLINE"] == "unproven"


def test_the_operator_list_has_the_differences_and_says_nothing_is_confirmed():
    rows = [{"id": "a1", "event": "Open Award", "market": "Cybersecurity", "field": "SUBMISSION DEADLINE", "claimed": "2026-12-01", "reader_value": "2026-12-02", "status": "differs", "tier": "x",
             "quote": "Entries close December 2, 2026.", "why": "ok", "pages": "https://a.example/enter"}]
    md = K.disagreements_md(rows, {"stamp": "s", "events": 1, "read": 1, "usd": 0.001})
    assert "DIFFERS" in md and "NOTHING here is confirmed" in md and "Entries close December 2, 2026." in md and "pin" in md
