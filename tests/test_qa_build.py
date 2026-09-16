"""The build step's QA report reads what the customer will see, and cries wolf as little as possible.

Its first run, on the real 2026-09-01 and 2026-09-14 pages, called 11 renames "removed" - a report
that warns eleven times about nothing is not read the twelfth. These pin the matching that fixed
it, and the warnings that are worth a person's attention before a page is sent.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import qa_report                                # noqa: E402

_spec = importlib.util.spec_from_file_location("qb", ROOT / "scripts" / "qa_build.py")
qb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qb)

ON = date(2026, 9, 21)


def _row(n, m="Utility", **kw):
    r = {"n": n, "m": m, "op": "Speaking", "url": f"https://{n.split()[0].lower()}.example/",
         "dl": "", "s": "Upcoming", "c": "Verified", "chk": "", "st": "Active",
         "dead": "False", "evdead": "False", "urldead": "False", "spon": "False", "lq": ""}
    r.update(kw)
    return r


def _page(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text(f"<html><script>const DATA = {json.dumps(rows)};\nconst X = 1;</script></html>",
                 encoding="utf-8")
    return p


def _run(prev, cur):
    return qb.compare(cur, prev, ON, "conference")


def test_the_page_is_read_back_exactly(tmp_path):
    p = _page(tmp_path, "Conference Review 2026-09-21 - Live Markets.html", [_row("ADIPEC 2026")])
    assert qb.page_data(p)[0]["n"] == "ADIPEC 2026" and qb.page_date(p) == ON


def test_a_bracketed_gloss_dropped_is_a_rename_not_a_removal():
    """The real case: 'ADIPEC 2026 (Abu Dhabi International ...)' became 'ADIPEC 2026'."""
    res = _run([_row("ADIPEC 2026 (Abu Dhabi International Petroleum Exhibition & Conference)",
                     url="https://a.example/")],
               [_row("ADIPEC 2026", url="https://b.example/")])
    assert not res["flags"]
    assert [c[2] for c in res["changes"]] == ["renamed"]


def test_the_same_website_is_the_same_event_whatever_it_is_called():
    """Decarb Connect Canada -> Industry Connect Canada: a real rebrand, one website."""
    res = _run([_row("Decarb Connect Canada 2026", url="https://decarbconnect.example/ca")],
               [_row("Industry Connect Canada 2026", url="https://decarbconnect.example/ca/")])
    assert not res["flags"] and res["changes"][0][2] == "renamed"


def test_a_changed_opportunity_label_is_named_as_that():
    res = _run([_row("it-sa Expo & Congress 2026", m="Cybersecurity")],
               [_row("it-sa Expo & Congress 2026", m="Cybersecurity", op="Exhibiting")])
    assert [c[2:] for c in res["changes"]] == [["opportunity type", "Speaking", "Exhibiting"]]


def test_a_row_that_really_disappeared_is_flagged():
    res = _run([_row("Alpha Summit", url="https://alpha.example/"),
                _row("Gamma Forum", url="https://gamma.example/")],
               [_row("Alpha Summit", url="https://alpha.example/")])
    assert any("Gamma Forum" in f and "gone" in f for f in res["flags"])


def test_a_deadline_moving_earlier_is_flagged_and_later_is_not():
    """Earlier is the dangerous direction: someone planning to the old date misses it."""
    res = _run([_row("SecTor 2026", dl="2026-12-15"), _row("Other", dl="2026-10-01")],
               [_row("SecTor 2026", dl="2026-11-26"), _row("Other", dl="2026-10-20")])
    assert len([f for f in res["flags"] if "EARLIER" in f]) == 1
    assert any("SecTor" in f for f in res["flags"])


def test_an_open_row_with_a_passed_deadline_is_flagged():
    res = _run(None, [_row("Late Call", s="Open", dl="2026-09-15")])
    assert any("shows Open with a deadline 6 day(s) past" in f for f in res["flags"])


def test_a_retired_opportunity_label_on_the_page_is_flagged():
    res = _run(None, [_row("SIEW 2026", op="Registration")])
    assert any("v2.5 retired" in f for f in res["flags"])


def test_a_disputed_deadline_and_a_dead_link_on_an_open_call_are_flagged():
    res = _run(None, [_row("A", chk="contradicted"), _row("B", s="Open", urldead="True",
                                                         dl="2026-12-01")])
    assert any("DISPUTES" in f for f in res["flags"]) and any("link is dead" in f for f in res["flags"])


def test_a_clean_week_passes(tmp_path):
    rows = [_row("Alpha Summit", dl="2026-12-01")]
    cur = _page(tmp_path, "Conference Review 2026-09-21 - Live Markets.html", rows)
    prev = _page(tmp_path, "Conference Review 2026-09-14 - Live Markets.html", rows)
    rep = qb.build([("conference", cur, prev)], ON, published=True)
    assert rep["status"] == "PASS" and rep["cycle"] == "2026-09-21"


def test_an_unpublished_build_says_so_first(tmp_path):
    cur = _page(tmp_path, "Conference Review 2026-09-21 - Live Markets.html", [_row("A")])
    rep = qb.build([("conference", cur, None)], ON, published=False)
    assert rep["status"] == "FLAG" and rep["flags"][0].startswith("NOT PUBLISHED")


def test_work_folders_are_never_treated_as_published(tmp_path):
    (tmp_path / "2026-09-14").mkdir()
    (tmp_path / "work_2026-09-21").mkdir()
    _page(tmp_path / "2026-09-14", "Conference Review 2026-09-14 - Live Markets.html", [])
    _page(tmp_path / "work_2026-09-21", "Conference Review 2026-09-21 - Live Markets.html", [])
    assert [p.parent.name for p in qb.published_pages("conference", tmp_path)] == ["2026-09-14"]


def test_every_step_of_one_week_files_under_the_same_monday():
    """Saturday intake, Sunday verify and Monday build belong to one cycle."""
    assert {qa_report.cycle_of(date(2026, 9, d)) for d in (19, 20, 21)} == {date(2026, 9, 21)}
    assert qa_report.cycle_of(date(2026, 9, 16)) == date(2026, 9, 21)
