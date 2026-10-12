"""ACT-67: the guarded first load of a brand-new AWARD in scripts/weekend_import.py (the awards equivalent of ACT-63; default OFF), and what ACT-66's Fast Company case teaches.

Offline. The gate and the subprocess steps are stubs; the database is a tiny sqlite file made with the real schema. What is proved: a new award whose id upstream gave us (ledger market 'Awards')
loads under the guards; an award with no id, an id the ledger does not hold, an id of another market's ledger, or an edition that disagrees with the id year is NAMED as held with its reason
(never dropped silently); the path is OFF by default and has its own switch (flag or CFP_AWARDS_NEW_EVENTS=1); the read-back proof undoes a load that added anything unexpected; the real
import_awards lands the row under the GIVEN id and never mints one."""
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.weekend_import as wi                                   # noqa: E402
from scripts import import_awards as ia                               # noqa: E402
from src.cfp_monitor.storage import Store                             # noqa: E402

A = wi.AWARDS
NEW1, NEW2, NEW3 = "2027-alpha-prize-nan-awards", "2027-beta-prize-nan-awards", "2027-gamma-prize-nan-awards"
OLD = "2026-old-prize-nan-awards"
COLS = ["Market", "EVENT_ID", "CONFERENCE", "SUBMISSION URL", "STATUS DETAILS", "EDITION", "SUBMISSION DEADLINE", "STATUS", "OPPORTUNITY_TYPE"]


def write(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def world(tmp_path, ledger=((NEW1, A), (NEW2, A), (NEW3, A)), input_ids=(NEW1, NEW2, NEW3), edition="2027"):
    md = tmp_path / "markets"
    md.mkdir()
    rows = [["Cybersecurity", f"up-{i}", f"{n} Prize", f"https://e.test/{i}", "", edition, "", "", "Awards"] for i, n in enumerate(["Alpha", "Beta", "Gamma", "Delta"])]
    write(md / f"{A}_audited.csv", COLS, rows)
    ident = {"up-0": NEW1, "up-1": NEW2, "up-2": NEW3, "up-3": ""}                      # Delta: our input row has no id at all
    write(md / f"{A}_audited.identity.csv", ["OUTPUT_EVENT_ID", "EVENT_ID_CANON"], [[k, v] for k, v in ident.items()])
    write(md / f"{A}_input.csv", ["CONFERENCE", "EVENT_ID_CANON"], [[f"x{i}", c] for i, c in enumerate(input_ids)])
    led = tmp_path / "given_ids.csv"
    write(led, ["event_id", "market", "given_on", "source"], [[i, m, "2026-10-12", "t"] for i, m in ledger])
    db = tmp_path / "db.sqlite"
    Store(str(db)).db.close()
    con = sqlite3.connect(db)
    con.execute("alter table award_grounding_facts add column upstream_event_id TEXT")
    con.execute("insert into award_grounding_facts (event_id, name, upstream_event_id) values (?,?,?)", (OLD, "Old Prize", "up-old"))
    con.commit()
    con.close()
    return md, led, db


def resolve(tmp_path, monkeypatch, md, led, db, **cfg):
    def fake_gate(csv_path, cwd, log, network=True, db=None, market=None):
        js = csv_path.with_name(csv_path.stem + ".gate.json")
        js.write_text("{}", encoding="utf-8")
        return "ACCEPTED", [], js
    monkeypatch.setattr(wi, "gate", fake_gate)
    monkeypatch.setattr(wi, "run", lambda *a, **k: 0)
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    log: list[str] = []
    res = wi.resolve_market(A, md, work, db, {}, log, None, {"ledger": led, **cfg})
    res["_log"] = log
    return res


def held(res):
    return {h["canonical"] or h["conference"]: h["reason"] for h in res["new_events_held"]}


def test_default_off_a_given_id_waits_and_is_named(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db)
    assert res["status"] == "ACCEPTED" and res["new_events"] == []
    assert res["new_events_waiting"] == 3
    r = held(res)[NEW1]
    assert "given by upstream" in r and "OFF" in r and "no permanent id - cannot tell" not in r
    assert any("NEW EVENT HELD" in l and "Alpha Prize" in l for l in res["_log"]), "the log names each held award"


def test_enabled_a_new_award_with_a_given_id_loads_under_that_id(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW1, NEW2, NEW3]
    ids = {l.split(",")[0].strip('"'): l.split(",")[1].strip('"') for l in Path(res["ids_csv"]).read_text(encoding="utf-8").splitlines()[1:]}
    assert ids == {"up-0": NEW1, "up-1": NEW2, "up-2": NEW3}, "import_awards will land each row on the id the ledger gave"
    assert res["from_this_week"] == 3


def test_no_id_at_all_is_named_held_never_dropped_silently(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert "Delta Prize" in held(res) and "never derive an id" in held(res)["Delta Prize"]
    assert [h["conference"] for h in res["new_events_held"]] == ["Delta Prize"]
    assert not any(r["CONFERENCE"] == "Delta Prize" for r in csv.DictReader(open(res["candidate"], encoding="utf-8")))


def test_an_id_the_awards_ledger_does_not_hold_stays_held(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, ledger=((NEW1, A),))
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW1]
    assert "not in the given_ids ledger" in held(res)[NEW2]


def test_the_conference_ledger_does_not_count_for_an_award(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, ledger=((NEW1, "Cybersecurity"), (NEW2, "Utility")))
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert res["new_events"] == []


def test_an_edition_that_disagrees_with_the_id_year_is_held_for_a_person(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, edition="2026")
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert res["new_events"] == [] and res["new_events_held_for_person"] == 3
    assert "carries 2027" in held(res)[NEW1]


def test_the_cap_is_respected(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True, cap=2)
    assert len(res["new_events"]) == 2 and "cap of 2" in held(res)[NEW3]


def test_an_award_already_in_the_database_is_not_a_new_event(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, input_ids=(NEW1, NEW2, NEW3))
    con = sqlite3.connect(db)
    con.executemany("insert into award_grounding_facts (event_id, name) values (?, 'x')", [(NEW1,), (NEW2,), (NEW3,)])
    con.commit()
    con.close()
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert res["new_events"] == [] and [h["conference"] for h in res["new_events_held"]] == ["Delta Prize"]


def test_read_back_proof_for_new_awards(tmp_path):
    db = tmp_path / "d.sqlite"
    Store(str(db)).db.close()
    con = sqlite3.connect(db)
    con.execute("insert into award_grounding_facts (event_id, name) values ('old', 'Old')")
    con.commit()
    before = wi.award_ids(db)
    con.execute("insert into award_grounding_facts (event_id, name) values (?, 'Alpha Prize')", (NEW1,))
    con.execute("insert into award_markets (award_key, market) values (?, 'Cybersecurity')", (NEW1,))
    con.commit()
    res = {"new_events": [{"canonical": NEW1, "conference": "Alpha Prize"}]}
    assert wi.prove_first_awards(res, before, db, True) is None
    assert "does not match" in wi.prove_first_awards({"new_events": [{"canonical": NEW1, "conference": "Zed"}]}, before, db, True)
    assert "not expected" in wi.prove_first_awards({"new_events": []}, before, db, True), "an id nobody expected means a minted id: undo the load"
    assert wi.prove_first_awards({"new_events": []}, before, db, False) is None                 # path off: behaves as before
    assert "not in the database" in wi.prove_first_awards({"new_events": [{"canonical": NEW2, "conference": "Beta"}]}, before, db, False)
    con.execute("delete from award_markets")
    con.commit()
    assert "no market list" in wi.prove_first_awards(res, before, db, True)
    con.close()


def test_import_awards_lands_the_row_under_the_given_id_and_never_mints(tmp_path):
    """The real importer: a new row with a carried id is inserted under THAT id; a row with no carried id would be minted from its name, which is why weekend_import never lets one through."""
    cols = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "EDITION", "Market", "OPPORTUNITY_TYPE", "CITY", "LOCATION", "MAIN_INFO_URL", "SUBMISSION DEADLINE", "STATUS"]
    d = tmp_path / "Awards_out.csv"
    write(d, cols, [["up-0", "Alpha Prize", "https://a.test", "2027", "Cybersecurity", "Awards", "", "", "", "", ""]])
    db = tmp_path / "t.db"
    Store(str(db)).db.close()
    planned, problems, _ = ia.plan(d, str(db), None, {"up-0": NEW1})
    assert not problems and [p["event_id"] for p in planned] == [NEW1] and planned[0]["_new"]
    ins, upd, _ = ia.apply(str(db), planned, "weekly-awards-test")
    assert (ins, upd) == (1, 0) and ia.reconcile(str(db), planned) == []
    con = sqlite3.connect(db)
    assert con.execute("select event_id, upstream_event_id from award_grounding_facts").fetchall() == [(NEW1, "up-0")]
    assert con.execute("select award_key, market from award_markets").fetchall() == [(NEW1, "Cybersecurity")]


def test_awards_switch_is_separate_from_the_conference_one_and_can_come_from_the_environment(tmp_path, monkeypatch):
    md, led, db0 = world(tmp_path)
    seen = {}
    cand = tmp_path / "cand.csv"
    cand.write_text("x", encoding="utf-8")

    def fake_resolve(m, markets_dir, work, db, up, log, ledger=None, first_load=None):
        seen[m] = first_load
        return {"market": m, "status": "ACCEPTED", "decisions": [], "candidate": str(cand), "ids_csv": "x", "accept_json": "x", "shipped": 1, "from_this_week": 1,
                "from_last_week": 0, "held_back": 0, "new_events": [], "new_events_held": [{"conference": "Delta Prize", "canonical": "", "reason": "no id"}]}

    called = {}
    monkeypatch.setattr(wi, "resolve_market", fake_resolve)
    monkeypatch.setattr(wi, "check_research", lambda *a, **k: None)
    monkeypatch.setattr(wi, "seed_map", lambda db: ({}, []))
    monkeypatch.setattr(wi, "assert_mapped", lambda *a, **k: None)
    monkeypatch.setattr(wi, "load_markets", lambda resolved, db, root, log, on=False, awards_on=False: called.update(on=on, awards_on=awards_on))
    monkeypatch.setattr(wi, "run", lambda *a, **k: 0)
    live = tmp_path / "live"
    (live / "market_sheets").mkdir(parents=True)
    (live / "cfp_monitor.db").write_bytes(db0.read_bytes())

    def go(extra, env=None):
        seen.clear(), called.clear()
        monkeypatch.delenv("CFP_AWARDS_NEW_EVENTS", raising=False)
        if env:
            monkeypatch.setenv("CFP_AWARDS_NEW_EVENTS", env)
        monkeypatch.setattr(sys, "argv", ["weekend_import.py", "--markets", A, "Cybersecurity", "--research-exit", "0", "--markets-dir", str(md), "--live", str(live),
                                          "--sandbox", str(tmp_path / "sb"), "--report", str(tmp_path / "r.json"), "--given-ids", str(led)] + extra)
        assert wi.main() == 0
    go([])
    assert seen[A]["enabled"] is False and seen["Cybersecurity"]["enabled"] is False and called == {"on": False, "awards_on": False}
    go(["--new-awards"])
    assert seen[A]["enabled"] is True and seen["Cybersecurity"]["enabled"] is False, "the awards switch does not turn the conference path on"
    assert called == {"on": False, "awards_on": True}
    go([], env="1")
    assert seen[A]["enabled"] is True and called["awards_on"] is True
    go(["--new-events"])
    assert seen["Cybersecurity"]["enabled"] is True and seen[A]["enabled"] is False, "--new-events is the conference switch only"


def test_the_final_report_names_held_new_awards(tmp_path, monkeypatch, capsys):
    md, led, db0 = world(tmp_path)
    cand = tmp_path / "cand.csv"
    cand.write_text("x", encoding="utf-8")
    monkeypatch.setattr(wi, "resolve_market", lambda m, *a, **k: {"market": m, "status": "ACCEPTED", "decisions": [], "candidate": str(cand), "ids_csv": "x", "accept_json": "x", "shipped": 1,
                                                                   "from_this_week": 1, "from_last_week": 0, "held_back": 1, "new_events": [],
                                                                   "new_events_held": [{"conference": "Delta Prize", "canonical": "", "reason": "no id"}]})
    monkeypatch.setattr(wi, "check_research", lambda *a, **k: None)
    monkeypatch.setattr(wi, "seed_map", lambda db: ({}, []))
    monkeypatch.setattr(wi, "assert_mapped", lambda *a, **k: None)
    monkeypatch.setattr(wi, "load_markets", lambda *a, **k: None)
    monkeypatch.setattr(wi, "run", lambda *a, **k: 0)
    live = tmp_path / "live"
    (live / "market_sheets").mkdir(parents=True)
    (live / "cfp_monitor.db").write_bytes(db0.read_bytes())
    monkeypatch.setattr(sys, "argv", ["weekend_import.py", "--markets", A, "--research-exit", "0", "--markets-dir", str(md), "--live", str(live), "--sandbox", str(tmp_path / "sb"),
                                      "--report", str(tmp_path / "r.json")])
    wi.main()
    out = capsys.readouterr().out
    assert "NEW AWARDS HELD Awards: 1 researched but not loaded" in out and "Delta Prize" in out
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["markets"][0]["new_events_held"][0]["conference"] == "Delta Prize"


# ---------------------------------------------------------------- ACT-66's Fast Company case: why a researched award vanished on 2026-10-09
def test_a_failure_about_the_stale_2026_row_no_longer_takes_the_freshly_researched_2027_row():
    """The gate cuts a name at 40 characters. 'Fast Company Most Innovative Companies 2026' (a carried-over row, deadline 2026-10-02, Open) failed check 6; the failure text starts with
    'Fast Company Most Innovative Companies 2' and so also matched the researched '... 2027 (anticipated cycle)' row (deadline 2026-10-09). That row was swapped for its own old copy, which failed
    the same way, and was dropped. The date in the failure text now tells the two apart."""
    stale = {"CONFERENCE": "Fast Company Most Innovative Companies 2026", "SUBMISSION DEADLINE": "2026-10-02", "STATUS": "Open"}
    fresh = {"CONFERENCE": "Fast Company Most Innovative Companies 2027 (anticipated cycle)", "SUBMISSION DEADLINE": "2026-10-09", "STATUS": "Open"}
    other = {"CONFERENCE": "Fast Company World Changing Ideas", "SUBMISSION DEADLINE": "2025-12-12", "STATUS": "Closed"}
    text = "Fast Company Most Innovative Companies 2: 2026-10-02 but STATUS=Open"
    assert wi.rows_for_failure(text, [stale, fresh, other]) == [0]
    assert wi.rows_for_failure(text, [fresh, stale, other]) == [1]
    # when no row carries the date, or the text has no date, the old greedy rule stands (holding a passing row is cheaper than shipping a failing one)
    assert wi.rows_for_failure("Fast Company Most Innovative Companies 2: 2031-01-01 but STATUS=Open", [stale, fresh]) == [0, 1]
    assert wi.rows_for_failure("Fast Company Most Innovative Companies 2: something without a date", [stale, fresh]) == [0, 1]
    assert wi.rows_for_failure("Fast Company World Changing Ideas: 2025-12-12 closed", [stale, fresh, other]) == [2]
