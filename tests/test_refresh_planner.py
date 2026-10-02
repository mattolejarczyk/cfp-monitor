"""scripts/refresh_planner.py implements docs/design/page-refresh-policy.md; one test per rule in that table (2026-10-02)."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("rp", ROOT / "scripts" / "refresh_planner.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)

TODAY = date(2026, 10, 5)


def ev(**kw):
    base = {"event_id": "e", "conference_key": "x.org", "name": "X", "start_date": "", "deadline": "", "url": "https://x.org/",
            "key_year": "2026", "imported_at": "2026-09-01", "lifecycle_quote": ""}
    base.update(kw)
    return base


def test_A_call_open_is_weekly():
    c = rp.classify(ev(start_date="2027-03-01", deadline="2026-10-20"), TODAY, [])
    assert (c["category"], c["interval_days"]) == ("A", 7)
    assert rp.classify(ev(start_date="2027-03-01", deadline="2026-10-05"), TODAY, [])["category"] == "A"      # today still open


def test_B_event_within_six_months():
    closed = rp.classify(ev(start_date="2026-12-01", deadline="2026-09-01"), TODAY, [])
    assert (closed["category"], closed["interval_days"]) == ("B", 14)
    nodate = rp.classify(ev(start_date="2026-12-01"), TODAY, [])
    assert (nodate["category"], nodate["interval_days"]) == ("B", 7)                                          # weekly when no deadline


def test_C1_cooling_off_then_C2_monthly():
    c1 = rp.classify(ev(start_date="2026-09-20", deadline="2026-06-01"), TODAY, [])
    assert c1["category"] == "C1" and c1["not_before"] == date(2026, 11, 6)   # starts 20 Sep, over 22 Sep, +45 days = 6 Nov
    assert rp.classify(ev(start_date="2026-05-01", deadline="2026-01-01"), TODAY, [])["category"] == "C2"
    assert rp.classify(ev(start_date="2026-05-01"), TODAY, [])["interval_days"] == 30


def test_D_dates_known_monthly_unknown_waits_45_days_then_biweekly():
    known = rp.classify(ev(start_date="2027-06-01", deadline="2026-09-01"), TODAY, [])
    assert (known["category"], known["interval_days"]) == ("D", 30)
    unknown = rp.classify(ev(start_date="2027-06-01", imported_at="2026-09-20"), TODAY, [])
    assert (unknown["category"], unknown["interval_days"]) == ("D", 14) and unknown["not_before"] == date(2026, 11, 4)


def test_E_unknown_event_date_is_an_exception_not_a_schedule():
    c = rp.classify(ev(start_date=""), TODAY, [])
    assert c["category"] == "E" and c["interval_days"] is None


def test_F_quarterly_and_never_after_two_years():
    assert rp.classify(ev(start_date="2026-03-01", lifecycle_quote="discontinued"), TODAY, [])["interval_days"] == 91
    old = rp.classify(ev(start_date="2024-01-01", lifecycle_quote="discontinued"), TODAY, [])
    assert old["category"] == "F" and old["interval_days"] is None and "never" in old["reason"]


def test_customer_skip_only_when_every_customer_is_done():
    e = ev(start_date="2027-03-01", deadline="2026-10-20")
    done = [{"status": "Submitted", "priority": "", "withdrawn_by_customer": 0}, {"status": "Accepted", "priority": "", "withdrawn_by_customer": 0}]
    assert rp.classify(e, TODAY, done)["category"] == "SKIP"
    one_open = done + [{"status": "Info Needed", "priority": "", "withdrawn_by_customer": 0}]
    assert rp.classify(e, TODAY, one_open)["category"] == "A"
    withdrawn = [{"status": "", "priority": "", "withdrawn_by_customer": 1}]
    assert rp.classify(e, TODAY, withdrawn)["category"] == "SKIP"
    assert rp.classify(e, TODAY, [])["category"] == "A"                  # nobody tracks it: keeps its category rate


def test_urgent_from_any_customer_raises_one_step():
    e = ev(start_date="2026-12-01", deadline="2026-09-01")               # B, 14 days
    urgent = [{"status": "Info Needed", "priority": "Urgent", "withdrawn_by_customer": 0}]
    c = rp.classify(e, TODAY, urgent)
    assert c["interval_days"] == 7 and "raised one step" in c["reason"]
    low = [{"status": "Info Needed", "priority": "Low", "withdrawn_by_customer": 0}]
    assert rp.classify(e, TODAY, low)["interval_days"] == 14


def test_step_ladder():
    assert rp.step_slower(7) == 14 and rp.step_slower(14) == 30 and rp.step_slower(30) == 30
    assert rp.step_faster(30) == 14 and rp.step_faster(14) == 7 and rp.step_faster(7) == 7


def test_due_rules():
    assert rp.due(7, None, date(2026, 9, 28), TODAY) == (True, "fetched 7 days ago, interval 7")
    assert rp.due(7, None, date(2026, 10, 1), TODAY)[0] is False
    assert rp.due(14, None, None, TODAY) == (True, "never fetched")
    assert rp.due(None, None, date(2026, 1, 1), TODAY)[0] is False
    assert rp.due(7, date(2026, 11, 1), date(2026, 1, 1), TODAY)[1].startswith("cooling off")
    assert rp.due(7, None, date(2026, 9, 28), TODAY, unchanged_fetches=True)[0] is False      # backs off 7 -> 14


def _dbs(tmp_path):
    db, lib = tmp_path / "c.db", tmp_path / "l.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id, conference_key, name, start_date, deadline, url, key_year, imported_at, lifecycle_quote)")
    con.execute("create table conference_markets (conference_key, market)")
    con.execute("create table client_conferences (event_id, client_key, status, priority, withdrawn_by_customer)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?,?,?,?,?)", [
        ("old-1", "a.org", "A old", "2025-01-01", "", "https://a.org", "2025", "2026-01-01", ""),
        ("new-1", "a.org", "A new", "2027-03-01", "2026-10-20", "https://a.org", "2027", "2026-09-01", ""),
        ("b-1", "other.net", "Other market", "2027-03-01", "2026-10-20", "https://other.net", "2027", "2026-09-01", "")])
    con.executemany("insert into conference_markets values (?,?)", [("a.org", "Cybersecurity"), ("other.net", "Robotics")])
    con.commit()
    con.close()
    lc = sqlite3.connect(lib)
    lc.execute("create table pages (url, host, tier, last_fetched_at, fetches, sha256)")
    lc.execute("create table page_versions (url, sha256)")
    lc.executemany("insert into pages values (?,?,?,?,?,?)", [
        ("https://a.org/cfp", "a.org", "P1", "2026-09-20T10:00:00Z", 1, "h1"),
        ("https://a.org/about", "a.org", "P2", "2026-10-04T10:00:00Z", 1, "h2"),
        ("https://zzz.example/", "zzz.example", "P2", "2026-09-01T10:00:00Z", 1, "h3")])
    lc.commit()
    lc.close()
    return str(db), str(lib)


def test_plan_uses_the_latest_edition_only_ignores_other_markets_and_lists_unmapped(tmp_path):
    db, lib = _dbs(tmp_path)
    plan = rp.make_plan(db, lib, TODAY)
    assert [e["event_id"] for e in plan["events"]] == ["new-1"]            # latest edition of a.org; other.net is Robotics
    assert plan["events"][0]["category"] == "A"
    due = {p["url"]: p["due"] for p in plan["pages"]}
    assert due == {"https://a.org/cfp": True, "https://a.org/about": False}   # 15 days vs 1 day against a 7-day interval
    assert [p["url"] for p in plan["unmapped"]] == ["https://zzz.example/"]


def test_render_runs_and_mentions_the_exception_batch(tmp_path):
    db, lib = _dbs(tmp_path)
    con = sqlite3.connect(db)
    con.execute("insert into grounding_facts values ('e-1','a.org','No date','','','https://a.org','2028','2026-09-01','')")
    con.commit()
    con.close()
    text = rp.render(rp.make_plan(db, lib, TODAY), TODAY, 5)
    assert "Refresh plan (shadow, report only)" in text and "Pages due this week" in text
