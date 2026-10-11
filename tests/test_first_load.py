"""ACT-63: the guarded first load of a brand-new event in scripts/weekend_import.py (default OFF).

Offline. The gate and the subprocess steps are replaced by stubs; the database is a tiny sqlite file. What is proved:
a new event whose id upstream gave us loads; an id the ledger does not hold stays held (honest reason); an id that
disagrees with our input row stays held; the cap is respected; the path is OFF by default; a second run adds
nothing; the sandbox never touches the live files.
"""
import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.weekend_import as wi                                   # noqa: E402
from scripts import first_load as fl                                  # noqa: E402

M = "Cybersecurity"
NEW1, NEW2, NEW3 = "2027-alpha-con-denver-speaking", "2027-beta-con-austin-speaking", "2027-gamma-con-miami-speaking"
COLS = ["Market", "EVENT_ID", "CONFERENCE", "CONFERENCE URL", "STATUS DETAILS", "EDITION", "START DATE"]


def write(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def world(tmp_path, ledger_ids=(NEW1, NEW2, NEW3), input_ids=(NEW1, NEW2, NEW3), db_ids_=("2027-old-con-reno-speaking",)):
    md = tmp_path / "markets"
    md.mkdir()
    rows = [[M, f"up-{i}", f"{n} Con", f"https://e.test/{i}", "", "2027", ""] for i, n in
            enumerate(["Alpha", "Beta", "Gamma", "Delta"])]
    write(md / f"{M}_audited.csv", COLS, rows)
    # identity: the id on the research row comes from OUR input row
    ident = {"up-0": NEW1, "up-1": NEW2, "up-2": NEW3, "up-3": "2027-delta-con-nowhere-speaking"}
    write(md / f"{M}_audited.identity.csv", ["OUTPUT_EVENT_ID", "EVENT_ID_CANON"], [[k, v] for k, v in ident.items()])
    write(md / f"{M}_input.csv", ["CONFERENCE", "EVENT_ID_CANON"], [[f"x{i}", c] for i, c in enumerate(input_ids)])
    led = tmp_path / "given_ids.csv"
    write(led, ["event_id", "market", "given_on", "source"], [[i, M, "2026-10-05", "t"] for i in ledger_ids])
    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text primary key, name text, url text)")
    for i in db_ids_:
        con.execute("insert into grounding_facts values (?,?,?)", (i, "Old Con", "https://old.test"))
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
    return wi.resolve_market(M, md, work, db, {}, [], None, {"ledger": led, **cfg})


def reasons(res):
    return {d["canonical"]: d["reasons"][0] for d in res["decisions"] if d["action"] == "held-back"}


def test_default_is_off_and_the_reason_is_true(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db)
    assert res["status"] == "ACCEPTED" and res["new_events"] == []
    assert res["new_events_waiting"] == 3
    r = reasons(res)[NEW1]
    assert "given by upstream" in r and "OFF" in r and "no permanent id" not in r
    # the argparse default is off too
    assert "--new-events" in Path(wi.__file__).read_text(encoding="utf-8")
    assert wi.argparse.ArgumentParser  # smoke
    src = Path(wi.__file__).read_text(encoding="utf-8")
    assert '"--new-events", action="store_true"' in src


def test_a_new_event_with_a_given_id_loads(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW1, NEW2, NEW3]
    ids = {l.split(",")[0].strip('"') for l in (Path(res["ids_csv"]).read_text(encoding="utf-8").splitlines()[1:])}
    assert ids == {"up-0", "up-1", "up-2"}
    assert res["from_this_week"] == 3
    # the 4th row's id is in neither the ledger nor the database: still held, with the honest old reason
    r = reasons(res)["2027-delta-con-nowhere-speaking"]
    assert "not in the given_ids ledger" in r


def test_unknown_id_stays_held_even_with_the_path_on(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, ledger_ids=(NEW1,))
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW1]
    assert "not in the given_ids ledger" in reasons(res)[NEW2]


def test_ledger_for_another_market_does_not_count(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    write(led, ["event_id", "market", "given_on", "source"], [[NEW1, "Utility", "2026-10-05", "t"]])
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert res["new_events"] == []


def test_id_not_on_our_input_row_stays_held(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, input_ids=(NEW2, NEW3))
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW2, NEW3]
    assert "not stamped on our input row" in reasons(res)[NEW1]


def test_cap_is_respected_and_the_rest_wait(tmp_path, monkeypatch):
    md, led, db = world(tmp_path)
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True, cap=2)
    assert len(res["new_events"]) == 2 and res["new_events_waiting"] == 1
    assert "cap of 2" in reasons(res)[NEW3]


def test_second_run_adds_nothing(tmp_path, monkeypatch):
    md, led, db = world(tmp_path, db_ids_=("2027-old-con-reno-speaking", NEW1, NEW2, NEW3))
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert res["new_events"] == [] and res["new_events_waiting"] == 0


def test_an_alias_of_a_held_event_is_not_loaded_as_new():
    ok, why = fl.decide(NEW1, enabled=True, ledger={NEW1}, input_ids={NEW1}, known=set(),
                        up_to_canon={NEW1: "2027-some-other-canonical"},
                        to_canonical=lambda e, m: m.get(e, e), taken=0, cap=100, edition="2027")
    assert not ok and "alias" in why


def test_edition_that_disagrees_with_the_id_year_stays_held(tmp_path, monkeypatch):
    # 2026-10-10 rehearsal: Upfront Summit was researched as the 2026 edition under a 2027 id; loading it fails invariant 7 and undoes everything.
    md, led, db = world(tmp_path)
    rows = list(csv.reader(open(md / f"{M}_audited.csv", encoding="utf-8")))
    rows[1][5] = "2026"                                   # Alpha: id 2027-..., edition 2026
    write(md / f"{M}_audited.csv", rows[0], rows[1:])
    res = resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [NEW2, NEW3]
    assert "carries 2027" in reasons(res)[NEW1]
    assert res["new_events_held_for_person"] == 1 and res["new_events_waiting"] == 0


def test_blank_id_is_never_loaded():
    ok, why = fl.decide("", enabled=True, ledger={""}, input_ids=set(), known=set(), up_to_canon={},
                        to_canonical=lambda e, m: e, taken=0, cap=100)
    assert not ok and "never derive an id" in why


def test_read_back_proof(tmp_path):
    db = tmp_path / "d.sqlite"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text primary key, name text, url text)")
    con.execute("insert into grounding_facts values ('old','Old','u')")
    con.commit()
    before = wi.db_ids(db)
    con.execute("insert into grounding_facts values (?,?,?)", (NEW1, "Alpha Con", "u"))
    con.commit()
    con.close()
    seed = tmp_path / "seed.csv"
    write(seed, ["EVENT_ID_CANON"], [[NEW1]])
    res = {"new_events": [{"canonical": NEW1, "conference": "Alpha Con"}]}
    assert wi.prove_first_loads(res, before, db, seed, True) is None
    # a seed row missing, a name that differs, and an id nobody expected each fail the proof
    write(seed, ["EVENT_ID_CANON"], [["other"]])
    assert "no seed row" in wi.prove_first_loads(res, before, db, seed, True)
    write(seed, ["EVENT_ID_CANON"], [[NEW1]])
    assert "does not match" in wi.prove_first_loads({"new_events": [{"canonical": NEW1, "conference": "Zed"}]}, before, db, seed, True)
    assert "not expected" in wi.prove_first_loads({"new_events": []}, before, db, seed, True)
    assert wi.prove_first_loads({"new_events": []}, before, db, seed, False) is None      # path off: behaves as before


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_sandbox_never_touches_the_live_files(tmp_path, monkeypatch):
    live = tmp_path / "live"
    (live / "market_sheets").mkdir(parents=True)
    md, led, db0 = world(tmp_path)
    (live / "cfp_monitor.db").write_bytes(db0.read_bytes())
    (live / "market_sheets" / "cyber_seed.csv").write_text("EVENT_ID_CANON\n", encoding="utf-8")
    before = {p.name: sha(p) for p in live.rglob("*") if p.is_file()}
    cand = tmp_path / "cand.csv"
    cand.write_text("x", encoding="utf-8")
    seen = {}

    def fake_resolve(m, markets_dir, work, db, up, log, ledger=None, first_load=None):
        seen["db"], seen["fl"] = Path(db), first_load
        return {"market": m, "status": "ACCEPTED", "decisions": [], "candidate": str(cand), "ids_csv": "x",
                "accept_json": "x", "shipped": 1, "from_this_week": 1, "from_last_week": 0, "held_back": 0,
                "new_events": [{"canonical": NEW1, "conference": "Alpha Con"}]}

    called = {}
    monkeypatch.setattr(wi, "resolve_market", fake_resolve)
    monkeypatch.setattr(wi, "check_research", lambda *a, **k: None)
    monkeypatch.setattr(wi, "seed_map", lambda db: ({}, []))
    monkeypatch.setattr(wi, "assert_mapped", lambda *a, **k: None)
    monkeypatch.setattr(wi, "load_markets", lambda resolved, db, root, log, on=False: called.update(db=Path(db), on=on))
    monkeypatch.setattr(wi, "run", lambda *a, **k: 0)
    sb = tmp_path / "sb"
    monkeypatch.setattr(sys, "argv", ["weekend_import.py", "--markets", M, "--research-exit", "0", "--markets-dir", str(md),
                                      "--live", str(live), "--sandbox", str(sb), "--report", str(tmp_path / "r.json"),
                                      "--new-events", "--new-events-cap", "7", "--given-ids", str(led)])
    assert wi.main() == 0
    assert seen["db"] == sb / "cfp_monitor.db" and called["db"] == sb / "cfp_monitor.db" and called["on"] is True
    assert seen["fl"] == {"enabled": True, "cap": 7, "ledger": led}
    assert {p.name: sha(p) for p in live.rglob("*") if p.is_file()} == before
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["mode"] == "sandbox"
