"""scripts/luna_shadow.py (ACT-61): fake Codex, fixture pages, scratch database. No network, no Codex, no model."""
import argparse
import csv
import json
import sqlite3

import pytest

from experiments.model_bakeoff import bakeoff_lib as B
from scripts import luna_shadow as LS

TODAY = "2026-10-10"
PAGE = "Alpha Summit 2026. 14 - 15 November 2026 Toronto, Canada. Organised by Acme Events. " + "filler about the programme. " * 20


def _approved(tmp, rows):
    cols = ["CONFERENCE", "EVENT_ID", "STATUS", "EDITION", "START DATE", "CITY", "COUNTRY", "LOCATION", "ORGANIZER", "FORMAT", "MAIN_INFO_URL"]
    d = tmp / "markets"
    d.mkdir()
    with open(d / "Utility_audited.final.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({"STATUS": "Upcoming", "EDITION": "2026", "MAIN_INFO_URL": f"https://x.example/{r['EVENT_ID']}", **r})
    return d


def _db(tmp, linked=()):
    p = tmp / "copy.db"
    con = sqlite3.connect(p)
    con.execute("create table grounding_facts (event_id text, name text, start_date text, city text, country text, organizer text)")
    con.execute("create table client_conferences (client_key text, event_id text)")
    con.execute("insert into grounding_facts values ('e1','Alpha','2026-11-14','Toronto','Canada','Acme Events')")
    for e in linked:
        con.execute("insert into client_conferences values ('arnica', ?)", (e,))
    con.commit()
    con.close()
    return p


def _args(tmp, markets, db, **kw):
    d = dict(markets=["Utility"], markets_dir=str(markets), db=str(db), token_budget=1500000, max_minutes=45, limit=0, today=TODAY, reader_dir=str(tmp / "none"), reader_json="",
             registry=str(tmp / "registry.jsonl"), out_dir=str(tmp / "out"), run_log=None, total_hours=4.6)
    d.update(kw)
    return argparse.Namespace(**d)


def _luna(answer=None, tokens=16000):
    ans = answer if answer is not None else {"start_date": {"value": "2026-11-14", "quote": "14 - 15 November 2026 Toronto, Canada"}, "city": {"value": "Toronto", "quote": "14 - 15 November 2026 Toronto, Canada"},
                                             "country": {"value": "Canada", "quote": "Toronto, Canada"}, "organizer": {"value": "Acme Events", "quote": "Organised by Acme Events"}}
    calls = []

    def ask(msgs, tag, timeout):
        calls.append(msgs)
        return {"parsed": ans, "raw": json.dumps(ans), "tokens": tokens, "seconds": 1.0, "status": 200, "error": "", "cost": 0.0}
    ask.calls = calls
    return ask


SIGNED = lambda: (True, "Logged in using ChatGPT")      # noqa: E731
pages = lambda row, cache: [(row["_urls"][0], PAGE)]    # noqa: E731


def _rows(n=3, **first):
    return [{"CONFERENCE": f"Event {i}", "EVENT_ID": f"e{i}", "START DATE": f"2026-1{i}-14", **(first if i == 1 else {})} for i in range(1, n + 1)]


def test_summary_line_format_and_report(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(1)), _db(tmp_path)
    reader = tmp_path / "reader.json"
    reader.write_text(json.dumps({"events": [{"id": "e1", "fields": {"start_date": {"reader": "2026-11-14", "quote": "x", "url": "u"}, "city": {"reader": "Ottawa", "quote": "held in Ottawa", "url": "u"},
                                                                       "format": {"reader": "In-Person", "quote": "in person", "url": "u"}}}]}), encoding="utf-8")
    assert LS.run(_args(tmp_path, m, db, reader_json=str(reader)), SIGNED, _luna(), pages) == 0
    out = capsys.readouterr().out
    line = [x for x in out.splitlines() if x.startswith("LUNA SHADOW:")][0]
    assert line == "LUNA SHADOW: 6 facts read, agree 1, disagree 1, Luna-only found 2, reader-only found 1, tokens 16000 (budget 1500000)"
    md = (tmp_path / "out" / "luna_shadow.md").read_text(encoding="utf-8")
    assert "Disagreements between Luna and the existing reader (1)" in md and "Luna **Toronto**, existing reader **Ottawa**" in md
    rows = [json.loads(x) for x in (tmp_path / "registry.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 6 and {r["model_key"] for r in rows} == {"luna-shadow"} and all(r["key_value"] == "" for r in rows)
    city = [r for r in rows if r["fact"] == "city"][0]
    assert city["db_value"] == "Toronto" and city["reader_value"] == "Ottawa" and city["accepted"] == "Toronto" and city["quote_verbatim_on_page"] is True and city["verdict"] == "shadow-disagree"


def test_token_budget_stops_cleanly_and_says_so(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(3)), _db(tmp_path)
    ask = _luna(tokens=16000)
    LS.run(_args(tmp_path, m, db, token_budget=40000), SIGNED, ask, pages)
    out = capsys.readouterr().out
    assert len(ask.calls) == 2                                              # 2 calls = 32000; a third (average 16000) would pass 40000
    assert "tokens 32000 (budget 40000)" in out and "stopped: token budget reached (32000 used of 40000)" in out


def test_codex_error_is_isolated_exact_text_no_retry_exit_zero(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(3)), _db(tmp_path)
    n = []

    def failing(msgs, tag, timeout):
        n.append(1)
        raise B.CodexError("ERROR: You've hit your usage limit. Try again at Oct 16th, 2026 6:30 PM.\nsecond line")
    assert LS.run(_args(tmp_path, m, db), SIGNED, failing, pages) == 0
    out = capsys.readouterr().out
    assert len(n) == 1                                                       # no retry, no second event
    assert "LUNA SHADOW: stopped - ERROR: You've hit your usage limit. Try again at Oct 16th, 2026 6:30 PM. second line" in out
    assert "You've hit your usage limit. Try again at Oct 16th, 2026 6:30 PM.\nsecond line" in (tmp_path / "out" / "luna_shadow.md").read_text(encoding="utf-8")   # exact text in the report
    assert not (tmp_path / "registry.jsonl").exists()


def test_main_never_raises_even_on_a_broken_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(LS, "codex_status", SIGNED)
    monkeypatch.setattr("sys.argv", ["luna_shadow.py", "--db", str(tmp_path / "missing.db"), "--markets-dir", str(tmp_path), "--out-dir", str(tmp_path / "o"), "--registry", str(tmp_path / "r.jsonl")])
    assert LS.main() == 0
    assert capsys.readouterr().out.startswith("LUNA SHADOW: stopped - ")


def test_other_exception_types_also_stop_with_their_text(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(2)), _db(tmp_path)

    def boom(msgs, tag, timeout):
        raise FileNotFoundError("codex")
    LS.run(_args(tmp_path, m, db), SIGNED, boom, pages)
    assert "LUNA SHADOW: stopped - FileNotFoundError: codex" in capsys.readouterr().out


def test_not_signed_in_skips_without_calling_anything(tmp_path, capsys):
    called = []
    LS.run(_args(tmp_path, tmp_path, tmp_path / "x.db"), lambda: (False, "Not logged in"), lambda *a: called.append(1), lambda *a: called.append(1))
    assert capsys.readouterr().out.strip() == "LUNA SHADOW: skipped - codex not signed in"
    assert not called and not (tmp_path / "out").exists()


def test_not_signed_in_exact_summary(tmp_path, capsys):
    LS.run(_args(tmp_path, tmp_path, tmp_path / "x.db"), lambda: (False, "Not logged in"), None, None)
    assert capsys.readouterr().out.startswith("LUNA SHADOW: skipped - codex not signed in")


def test_priority_customer_then_next_60_days_then_rest():
    rows = [{"CONFERENCE": "Far", "EVENT_ID": "a", "START DATE": "2027-03-01", "STATUS": "Upcoming", "EDITION": "2027", "MAIN_INFO_URL": "https://x/a"},
            {"CONFERENCE": "Soon", "EVENT_ID": "b", "START DATE": "2026-10-20", "STATUS": "Upcoming", "EDITION": "2026", "MAIN_INFO_URL": "https://x/b"},
            {"CONFERENCE": "Cust", "EVENT_ID": "c", "START DATE": "2027-06-01", "STATUS": "Upcoming", "EDITION": "2027", "MAIN_INFO_URL": "https://x/c"},
            {"CONFERENCE": "SoonAnswered", "EVENT_ID": "d", "START DATE": "2026-12-05", "STATUS": "Upcoming", "EDITION": "2026", "MAIN_INFO_URL": "https://x/d"},
            {"CONFERENCE": "FarAnswered", "EVENT_ID": "e", "START DATE": "2027-09-01", "STATUS": "Upcoming", "EDITION": "2027", "MAIN_INFO_URL": "https://x/e"},
            {"CONFERENCE": "TooLate60", "EVENT_ID": "f", "START DATE": "2026-12-20", "STATUS": "Upcoming", "EDITION": "2026", "MAIN_INFO_URL": "https://x/f"}]
    sel = LS.pick_rows(rows, TODAY, {"CANON-C"}, {"c": "CANON-C"}, {"e"})
    assert [r["CONFERENCE"] for r in sel] == ["Cust", "Soon", "SoonAnswered", "FarAnswered", "TooLate60", "Far"]
    assert [r["_tier"] for r in sel] == [0, 1, 1, 2, 2, 2]
    assert len(LS.pick_rows(rows, TODAY, set(), {}, set(), limit=2)) == 2


def test_customer_linked_row_is_read_first_through_the_canonical_id(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(3)), _db(tmp_path, linked=["e3"])
    ask = _luna()
    LS.run(_args(tmp_path, m, db, limit=1), SIGNED, ask, pages)
    assert "Event 3" in (tmp_path / "registry.jsonl").read_text(encoding="utf-8")


def test_the_request_is_blind_only_event_edition_and_page(tmp_path):
    m, db = _approved(tmp_path, _rows(1)), _db(tmp_path)
    ask = _luna()
    LS.run(_args(tmp_path, m, db), SIGNED, ask, pages)
    msgs = ask.calls[0]
    assert [x["role"] for x in msgs] == ["system", "user"]
    header = msgs[1]["content"].split("PAGE TEXT:")[0]
    assert "Toronto" not in header and "2026-11-14" not in header and "Acme" not in header       # no db value, no other reader's answer


def test_a_quote_that_is_not_on_the_page_is_not_accepted(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(1)), _db(tmp_path)
    ans = {"city": {"value": "Paris", "quote": "held in Paris"}}
    LS.run(_args(tmp_path, m, db), SIGNED, _luna(ans), pages)
    rows = [json.loads(x) for x in (tmp_path / "registry.jsonl").read_text(encoding="utf-8").splitlines()]
    city = [r for r in rows if r["fact"] == "city"][0]
    assert city["accepted"] == "" and city["accept_why"] == "quote is not on the page"


def test_only_the_report_and_registry_are_written_and_the_database_is_untouched(tmp_path):
    m, db = _approved(tmp_path, _rows(2)), _db(tmp_path)
    before_db = db.read_bytes()
    before_approved = (m / "Utility_audited.final.csv").read_bytes()
    LS.run(_args(tmp_path, m, db), SIGNED, _luna(), pages)
    assert db.read_bytes() == before_db and (m / "Utility_audited.final.csv").read_bytes() == before_approved
    created = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert created == {"copy.db", "markets/Utility_audited.final.csv", "registry.jsonl", "out/luna_shadow.md", "pages/" + next(p.name for p in (tmp_path / "pages").iterdir())}


def test_max_minutes_stops(tmp_path, capsys):
    m, db = _approved(tmp_path, _rows(2)), _db(tmp_path)
    LS.run(_args(tmp_path, m, db, max_minutes=-1), SIGNED, _luna(), pages)
    assert "stopped: the -1-minute limit" in capsys.readouterr().out


def test_codex_status_reading(monkeypatch):
    class P:
        returncode, stdout, stderr = 0, "Logged in using ChatGPT\n", ""
    monkeypatch.setattr(LS.subprocess, "run", lambda *a, **k: P)
    assert LS.codex_status()[0] is True
    P.stdout = "Not logged in"
    assert LS.codex_status()[0] is False
    monkeypatch.setattr(LS.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("codex")))
    assert LS.codex_status()[0] is False
