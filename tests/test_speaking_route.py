"""scripts/speaking_route.py: how a company gets a speaking slot, and whether it must pay. Offline: no network, no model. The code (not the model) decides the label."""
import sqlite3
from datetime import date, datetime

import pytest

import scripts.speaking_route as sr


def pages(*texts, kinds=None):
    kinds = kinds or ["home", "call", "sponsor", "sponsor"]
    return [{"kind": kinds[i], "url": f"https://e.example/p{i}", "text": t} for i, t in enumerate(texts)]


CALL = "Call for Speakers: submit a talk proposal by 1 November 2026. Everyone is welcome to apply."
PAID = "Gold package: includes a 20 minute keynote speaking slot on the main stage."


def ans(**kw):
    base = {"open_call": "unclear", "open_call_quote": "", "paid_slots": "unclear", "paid_slots_quote": "", "must_pay": "unclear", "must_pay_quote": "", "summary": "x"}
    base.update(kw)
    return base


# ------------------------------------------------------------------ routes
def test_open_call_with_a_quote_that_says_it():
    r = sr.route(ans(open_call="yes", open_call_quote="submit a talk proposal by 1 November 2026"), pages(CALL), "2026")
    assert r["route"] == "OPEN_CALL" and r["dropped"] == []


def test_open_call_and_paid_slots():
    r = sr.route(ans(open_call="yes", open_call_quote="Call for Speakers", paid_slots="yes", paid_slots_quote="includes a 20 minute keynote speaking slot"), pages(CALL, PAID), "2026")
    assert r["route"] == "OPEN_CALL_AND_PAID_SLOTS"


def test_paid_slots_with_no_call_seen_is_not_called_open():
    r = sr.route(ans(paid_slots="yes", paid_slots_quote="includes a 20 minute keynote speaking slot"), pages(PAID), "2026")
    assert r["route"] == "PAID_SLOTS_NO_CALL_SEEN"


def test_must_sponsor_needs_a_quote_that_says_must():
    p = pages("Speaking slots are reserved for sponsors only.")
    assert sr.route(ans(must_pay="yes", must_pay_quote="Speaking slots are reserved for sponsors only."), p)["route"] == "MUST_SPONSOR"
    weak = sr.route(ans(must_pay="yes", must_pay_quote="Speaking slots are part of our sponsor package."), pages("Speaking slots are part of our sponsor package."))
    assert weak["route"] == "UNCLEAR" and any("does not say it" in d for d in weak["dropped"])


def test_a_quote_that_is_not_on_the_pages_is_dropped():
    r = sr.route(ans(open_call="yes", open_call_quote="Submit your abstract today"), pages("nothing about that here"))
    assert r["route"] == "UNCLEAR" and any("not on the pages" in d for d in r["dropped"])


def test_a_call_closed_notice_is_not_invitation_only():
    r = sr.route(ans(open_call="no", open_call_quote="Call for Papers has now closed! Stay tuned for the agenda!"), pages("Call for Papers has now closed! Stay tuned for the agenda!"))
    assert r["route"] == "UNCLEAR"                                          # closed is not invited; the first draft got this wrong


def test_invitation_only_needs_a_quote_that_says_invited():
    t = "Speakers are by invitation only, selected by our advisory board."
    assert sr.route(ans(open_call="no", open_call_quote=t), pages(t))["route"] == "INVITE_ONLY"
    t2 = "Speakers are by invitation only, but sponsors may buy a keynote speaking slot."
    r = sr.route(ans(open_call="no", open_call_quote="Speakers are by invitation only", paid_slots="yes", paid_slots_quote="sponsors may buy a keynote speaking slot"), pages(t2))
    assert r["route"] == "PAID_SLOTS_NO_CALL_SEEN"                           # paid slots are shown, not hidden under INVITE_ONLY


def test_a_call_dated_before_the_edition_is_dropped():
    t = "Call for Abstracts - Due July 30, 2021"
    r = sr.route(ans(open_call="yes", open_call_quote=t), pages(t), "2026")
    assert r["route"] == "UNCLEAR" and any("before the 2026 edition" in d for d in r["dropped"])
    assert sr.route(ans(open_call="yes", open_call_quote=t), pages(t), "")["route"] == "OPEN_CALL"        # no edition known: the year cannot be judged


def test_a_call_for_a_committee_is_not_a_call_for_speakers():
    t = "Call for Program Committee! Interest due by October 6, 2026"
    assert sr.route(ans(open_call="yes", open_call_quote=t), pages(t), "2027")["route"] == "UNCLEAR"
    t2 = "Call for Program Committee members and speakers"
    assert sr.route(ans(open_call="yes", open_call_quote=t2), pages(t2), "2027")["route"] == "OPEN_CALL"


def test_garbled_characters_are_cleaned_and_still_match():
    page = "ExtraÂ Benefit: speakingÂ slot included in the Gold sponsor package"
    r = sr.route(ans(paid_slots="yes", paid_slots_quote="speaking slot included in the Gold sponsor package"), pages(page))
    assert r["route"] == "PAID_SLOTS_NO_CALL_SEEN" and "Â" not in r["paid_quote"]
    assert sr.clean("a Â b\n c") == "a b c"


def test_nothing_proven_is_unclear_which_is_a_complete_answer():
    assert sr.route({}, pages("anything"))["route"] == "UNCLEAR"
    assert sr.route(ans(), pages("anything"))["route"] == "UNCLEAR"


# ------------------------------------------------------------------ page picking
def test_pick_prefers_pages_named_for_the_topic_and_skips_junk_and_excluded():
    urls = ["https://e.example/", "https://e.example/privacy-policy", "https://e.example/sponsorship-opportunities", "https://e.example/partners", "https://e.example/news/sponsor-announced",
            "https://e.example/prospectus.pdf", "https://e.example/call-for-speakers", "https://e.example/about"]
    spons = sr.pick(urls, {}, sr.SPONSOR_WORDS, {"https://e.example/"}, 3)
    assert spons[0].endswith("/sponsorship-opportunities") and not any("privacy" in u or "news" in u or u.endswith(".pdf") for u in spons)
    calls = sr.pick(urls, {}, sr.CALL_WORDS, set(spons) | {"https://e.example/"}, 3)
    assert calls == ["https://e.example/call-for-speakers"]


def test_pick_uses_link_text_too():
    assert sr.pick(["https://e.example/x1"], {"https://e.example/x1": "Become a Sponsor"}, sr.SPONSOR_WORDS, set(), 2) == ["https://e.example/x1"]


# ------------------------------------------------------------------ the table and which events get judged
def make_db(tmp_path, rows):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text, name text, url text, main_info_url text, sponsor_url text, sponsor_cost text, edition text, status text)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()
    return db


def row(i, status="Open", url="https://e.example/"):
    return (f"id{i}", f"Event {i}", url, "", "", "", "2026", status)


def test_load_routes_is_empty_when_the_table_does_not_exist(tmp_path):
    assert sr.load_routes(make_db(tmp_path, [row(1)])) == {}
    assert sr.load_routes(tmp_path / "missing.db") == {}


def test_store_then_load_keeps_the_quote_its_page_and_who_and_when(tmp_path):
    db = make_db(tmp_path, [row(1)])
    pg = pages(CALL)
    res = sr.route(ans(open_call="yes", open_call_quote="submit a talk proposal by 1 November 2026", summary="Submit a proposal."), pg, "2026")
    con = sqlite3.connect(db)
    sr.store(con, "id1", res, pg, "2026", (1200, 90), datetime(2026, 10, 19, 15, 0))
    con.close()
    got = sr.load_routes(db)["id1"]
    assert got["route"] == "OPEN_CALL" and got["call_url"] == "https://e.example/p0" and got["judged_at"] == "2026-10-19 15:00" and got["model"] == sr.MODEL_NAME
    assert got["call_quote"] == "submit a talk proposal by 1 November 2026" and got["tokens_in"] == 1200


def test_candidates_never_judged_first_live_before_closed_oldest_next_and_age_rules(tmp_path):
    db = make_db(tmp_path, [row(1, "Closed"), row(2, "Open"), row(3, "Open"), row(4, "Open"), row(5, "Open"), row(6, "Open", url="")])
    con = sqlite3.connect(db)
    old = sr.route(ans(open_call="yes", open_call_quote="Call for Speakers"), pages("Call for Speakers"))
    sr.store(con, "id3", old, pages("Call for Speakers"), "2026", (0, 0), datetime(2026, 9, 1, 9, 0))        # decided 48 days ago: still fresh at 56
    unclear = sr.route({}, pages("x"))
    sr.store(con, "id4", unclear, pages("x"), "2026", (0, 0), datetime(2026, 9, 1, 9, 0))                   # UNCLEAR 48 days ago: due (28 days)
    sr.store(con, "id5", old, pages("Call for Speakers"), "2026", (0, 0), datetime(2026, 7, 1, 9, 0))        # decided 110 days ago: due
    con.close()
    ids = {"id1", "id2", "id3", "id4", "id5", "id6"}
    out = sr.candidates(db, ids, date(2026, 10, 19))
    assert [r["event_id"] for r in out] == ["id2", "id1", "id5", "id4"]      # never judged (live first), then oldest first; id3 fresh; id6 has no home page
    assert [r["event_id"] for r in sr.candidates(db, {"id2"}, date(2026, 10, 19))] == ["id2"]                # only the customer markets
    assert len(sr.candidates(db, ids, date(2026, 10, 19), limit=2)) == 2
    assert [r["event_id"] for r in sr.candidates(db, ids, date(2026, 10, 19), only=["id3"])] == ["id3"]      # naming an event ignores the age rule


# ------------------------------------------------------------------ it can never fail a weekly job
def test_a_fault_prints_a_line_and_exits_zero(tmp_path, capsys):
    assert sr.main(["--db", str(tmp_path / "nope.db")]) == 0
    assert "SPEAKING ROUTE" in capsys.readouterr().out


def test_the_prompt_names_the_edition_and_asks_for_quotes():
    u = sr.build_user("Conf X", "2027", pages(CALL, kinds=["call"]))
    assert "EDITION: 2027" in u and "kind=call" in u
    assert "never reword" in sr.SYSTEM and "\"no\" ONLY if" in sr.SYSTEM


# ------------------------------------------------------------------ a failed read is not an answer (2026-10-19: a browser dialog crashed the driver and 117 events were recorded as UNCLEAR)
def test_an_unclear_event_where_no_page_could_be_read_is_retried_much_sooner(tmp_path):
    db = make_db(tmp_path, [row(1), row(2), row(3)])
    con = sqlite3.connect(db)
    nothing = sr.route({}, [{"kind": "home", "url": "u", "text": ""}])
    sr.store(con, "id1", nothing, [{"kind": "home", "url": "u", "text": ""}], "2026", (0, 0), datetime(2026, 10, 1, 9, 0))      # read nothing, 18 days ago: due (14)
    read = sr.route({}, pages("some text with nothing useful"))
    sr.store(con, "id2", read, pages("some text with nothing useful"), "2026", (0, 0), datetime(2026, 10, 1, 9, 0))              # read pages, found nothing, 18 days ago: not due (28)
    sr.store(con, "id3", nothing, [{"kind": "home", "url": "u", "text": ""}], "2026", (0, 0), datetime(2026, 10, 15, 9, 0))      # read nothing, 4 days ago: not due
    con.close()
    out = [r["event_id"] for r in sr.candidates(db, {"id1", "id2", "id3"}, date(2026, 10, 19))]
    assert out == ["id1"]


def test_the_run_stops_when_the_browser_layer_is_down_and_records_nothing_for_it():
    s = (sr.__file__ and open(sr.__file__, encoding="utf-8").read())
    assert "MAX_UNREADABLE_IN_A_ROW" in s and "the browser layer looks down" in s
    block = s[s.index('elif not any((p["text"] or "").strip() for p in pages):'):s.index('                else:\n                    state["consecutive_unreadable"] = 0')]
    assert 'if state["abort"]:' in block and "return" in block.split('if state["abort"]:')[1].split("res, toks")[0]      # an aborted run returns before store()
    assert "hard anti-bot host and no real Chrome reachable: not read" in s                                           # a skipped site is recorded, never left at the front of the queue


def test_the_page_renderer_swallows_a_javascript_dialog_instead_of_crashing_the_driver():
    f = open(sr.ROOT / "src" / "cfp_monitor" / "fetch.py", encoding="utf-8").read()
    assert 'page.on("dialog"' in f and "async def _dismiss_dialog" in f and "import asyncio" in f


def test_a_hard_anti_bot_host_is_read_through_the_real_chrome_when_it_is_reachable_and_never_with_plain_requests():
    src = open(sr.__file__, encoding="utf-8").read()
    body = src[src.index("async def collect("):src.index("async def ask(")]
    assert "ctx._f.cdp_reachable(" in body and "if hard and not" in body            # skipped only when there is no real Chrome
    assert "if not hard:" in body.split("urls, labels = [], {}")[1].split("cache:")[0]   # the plain-HTTP sitemap request is never made to such a host
    assert "prefer_cdp=True" in src                                                    # pages are rendered through the real browser first


def test_a_url_naming_an_earlier_year_is_an_old_edition_but_the_bare_page_is_evergreen():
    assert sr.old_edition_url("https://x.org/call-for-papers-2025", 2027)
    assert sr.old_edition_url("https://x.org/2026/cfp", 2027)
    assert not sr.old_edition_url("https://x.org/call-for-papers", 2027)
    assert not sr.old_edition_url("https://x.org/call-for-papers-2027", 2027)


def test_an_event_that_already_happened_is_not_a_candidate():
    src = open(sr.__file__, encoding="utf-8").read()
    assert 'str(r["start_date"])[:10] < today.isoformat()' in src


def test_the_floor_is_the_current_calendar_year_so_next_years_announcements_on_this_years_page_survive():
    src = open(sr.__file__, encoding="utf-8").read()
    assert "floor = date.today().year" in src
    assert sr.old_edition_url("https://x.org/2025/cfp", 2026) and not sr.old_edition_url("https://x.org/2026/cfp", 2026)
    assert sr.old_edition_url("https://x.org/2026/cfp", 2027)               # from 1 Jan 2027
