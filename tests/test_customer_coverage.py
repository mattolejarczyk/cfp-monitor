"""ACT-51: scripts/customer_coverage.py answers 'is every customer row in the research queue?'. FIXTURES ONLY: a throwaway database and input lists built in tmp_path."""
import csv
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import customer_coverage as cc          # noqa: E402
from scripts import add_customer_rows as acr          # noqa: E402

COLS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "START DATE", "EDITION", "Market", "RESEARCH STATUS", "EVENT_ID_CANON", "DUP_OF"]
TODAY = "2026-10-06"


def make_world(tmp_path, client_rows, cyb_inputs, util_inputs=(), seed=(("UP-1", "canon-1"),), ledger=()):
    data = tmp_path / "data"
    (data / "market_sheets").mkdir(parents=True)
    with open(data / "market_sheets" / "cyber_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["EVENT_ID", "EVENT_ID_CANON"])
        w.writerows(seed)
    db = data / "cfp.db"
    con = sqlite3.connect(db)
    con.execute("create table client_conferences (client_key text, their_name text, event_id text, their_url text, their_deadline text, status text, location text, "
                "event_start_date text, withdrawn_by_customer integer default 0)")
    for r in client_rows:
        con.execute("insert into client_conferences values (?,?,?,?,?,?,?,?,?)", (r.get("client_key", "arnica"), r["name"], r.get("event_id"), r.get("url", ""), r.get("deadline", ""),
                                                                                r.get("status", ""), r.get("loc", ""), r.get("start", ""), r.get("withdrawn", 0)))
    con.commit()
    con.close()
    md = tmp_path / "markets"
    md.mkdir()
    for market, rows in (("Cybersecurity", cyb_inputs), ("Utility", util_inputs)):
        with open(md / f"{market}_input.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLS})
    led = tmp_path / "ledger.csv"
    with open(led, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cc.LEDGER_COLS)
        w.writeheader()
        w.writerows(ledger)
    return db, md, led


def run(tmp_path, *a, **kw):
    db, md, led = make_world(tmp_path, *a, **kw)
    res, degraded, why = cc.run(db, md, led, TODAY)
    return res, degraded, why, (db, md, led)


def test_row_is_in_queue_by_event_id_even_when_the_input_carries_upstreams_spelling(tmp_path):
    res, _, _, _ = run(tmp_path, [{"name": "Alpha", "event_id": "canon-1", "url": "https://a.example/", "start": "12/01/2026"}],
                       [{"CONFERENCE": "Alpha Conf", "CONFERENCE URL": "https://other.example/", "EVENT_ID_CANON": "UP-1"}])
    assert [x["why"] for x in res["in_queue"]] == ["by event id"] and not res["not_in_queue"]


def test_unlinked_row_is_found_by_normalised_url(tmp_path):
    res, _, _, _ = run(tmp_path, [{"name": "Beta", "url": "http://www.beta.example/x/?utm=1", "start": "12/01/2026"}],
                       [{"CONFERENCE": "Beta 2026", "CONFERENCE URL": "https://beta.example/x"}])
    assert len(res["in_queue"]) == 1 and "by URL" in res["in_queue"][0]["why"]


def test_a_row_with_no_input_row_is_reported_not_in_queue_with_summary_and_first_five_names(tmp_path):
    rows = [{"name": f"Gone {i}", "url": f"https://g{i}.example/", "start": "12/01/2026"} for i in range(7)]
    res, _, _, _ = run(tmp_path, rows, [{"CONFERENCE": "Other", "CONFERENCE URL": "https://o.example/"}])
    lines = cc.summary_lines(res)
    assert lines[0] == "COVERAGE: 0 of 7 customer rows ahead of 2026-10-06 are in the research queue; 7 are NOT"
    assert lines[1] == "COVERAGE NOT IN QUEUE: Gone 0; Gone 1; Gone 2; Gone 3; Gone 4; and 2 more"


def test_same_domain_other_edition_url_is_not_treated_as_in_queue(tmp_path):
    res, _, _, _ = run(tmp_path, [{"name": "Gartner IAM", "url": "https://g.example/iam-2027", "start": "03/08/2027"}],
                       [{"CONFERENCE": "Gartner IAM 2026", "CONFERENCE URL": "https://g.example/iam-2026"}])
    assert len(res["not_in_queue"]) == 1


def test_every_exclusion_is_listed_with_its_reason(tmp_path):
    rows = [{"name": "Over", "url": "https://over.example/", "start": "09/01/2026"},
            {"name": "Withdrawn", "url": "https://w.example/", "start": "12/01/2026", "withdrawn": 1},
            {"name": "Ruled out", "url": "https://r.example/", "start": "12/01/2026"},
            {"name": "Dup", "url": "https://d.example/", "start": "12/01/2026"},
            {"name": "No date", "url": "https://nd.example/", "start": ""}]
    ledger = [{"event_name": "Ruled out", "url": "", "client": "arnica", "reason": "customer says not ours", "ruled_by": "Matt", "ruled_on": "2026-10-06"}]
    res, _, _, _ = run(tmp_path, rows, [{"CONFERENCE": "Dup row", "CONFERENCE URL": "https://d.example/", "DUP_OF": "x-1"}], ledger=ledger)
    why = {x["name"]: x["why"] for x in res["excluded"]}
    assert "event is over: starts 2026-09-01" in why["Over"]
    assert "withdrawn_by_customer" in why["Withdrawn"]
    assert "customer says not ours" in why["Ruled out"] and "Matt" in why["Ruled out"]
    assert "DUP_OF" in why["Dup"]
    assert [x["name"] for x in res["not_in_queue"]] == ["No date"]          # no date means ahead: finding it is research's job
    assert len(res["in_queue"]) == 0


def test_ledger_entry_for_another_client_does_not_exclude(tmp_path):
    ledger = [{"event_name": "X", "url": "", "client": "utility-global", "reason": "r", "ruled_by": "Matt", "ruled_on": "2026-10-06"}]
    res, _, _, _ = run(tmp_path, [{"name": "X", "start": "12/01/2026", "url": "https://x.example/"}], [], ledger=ledger)
    assert len(res["not_in_queue"]) == 1


def test_markets_are_kept_apart(tmp_path):
    res, _, _, _ = run(tmp_path, [{"client_key": "utility-global", "name": "U", "url": "https://u.example/", "start": "12/01/2026"}],
                       [{"CONFERENCE": "U", "CONFERENCE URL": "https://u.example/"}], util_inputs=[])
    assert len(res["not_in_queue"]) == 1                                    # on the Cybersecurity list, not Utility's


def test_proposal_csv_is_the_class_c_layout_and_add_customer_rows_accepts_it(tmp_path):
    res, _, _, _ = run(tmp_path, [{"name": "New Con", "url": "https://n.example/", "start": "02/17/2027", "loc": "Austin, TX", "deadline": "10/01/2026"}],
                       [{"CONFERENCE": "Other", "CONFERENCE URL": "https://o.example/"}])
    rows = cc.propose_rows(res)
    assert list(rows[0].keys()) == cc.PROPOSE_COLS and rows[0]["class"] == "C" and rows[0]["sheet"] == "arnica" and rows[0]["customer_start"] == "02/17/2027"
    cols = {"Cybersecurity": COLS + ["LATEST UPDATE"], "Utility": COLS}
    add, skipped = acr.plan(rows, {"Cybersecurity": [], "Utility": []}, cols, "2026-10-11")
    assert [r["CONFERENCE"] for r in add["Cybersecurity"]] == ["New Con"] and add["Cybersecurity"][0]["START DATE"] == "2/17/2027" and not skipped


def test_the_database_is_never_written(tmp_path):
    db, md, led = make_world(tmp_path, [{"name": "A", "url": "https://a.example/", "start": "12/01/2026"}], [])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    cc.run(db, md, led, TODAY)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before and not list(db.parent.glob("*-wal")) and not list(db.parent.glob("*-journal"))


def test_degraded_inputs_are_reported_and_the_exit_code_is_still_zero(tmp_path):
    res, _, why = cc.run(tmp_path / "nope.db", tmp_path, tmp_path / "l.csv", TODAY)
    assert res is None and "database not found" in why
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "customer_coverage.py"), "--db", str(tmp_path / "nope.db"), "--markets-dir", str(tmp_path)], capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.startswith("COVERAGE: UNKNOWN - database not found")


def test_missing_input_list_is_unknown_not_a_crash(tmp_path):
    db, md, led = make_world(tmp_path, [{"name": "A", "start": "12/01/2026"}], [])
    (md / "Utility_input.csv").unlink()
    res, _, why = cc.run(db, md, led, TODAY)
    assert res is None and "input list not found" in why


def test_empty_seed_map_is_flagged_as_degraded(tmp_path):
    res, degraded, _, _ = run(tmp_path, [{"name": "A", "start": "12/01/2026", "url": "https://a.example/"}], [], seed=())
    assert degraded and "seed map is empty" in degraded[0]


def test_command_line_writes_reports_and_proposal_and_exits_zero(tmp_path):
    db, md, led = make_world(tmp_path, [{"name": "In", "url": "https://i.example/", "start": "12/01/2026"}, {"name": "Out", "url": "https://out.example/", "start": "12/02/2026"}],
                             [{"CONFERENCE": "In", "CONFERENCE URL": "https://i.example/"}])
    out, prop = tmp_path / "qa", tmp_path / "prop.csv"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "customer_coverage.py"), "--db", str(db), "--markets-dir", str(md), "--ledger", str(led), "--today", TODAY,
                        "--out-dir", str(out), "--propose", str(prop)], capture_output=True, text=True)
    assert p.returncode == 0
    assert "COVERAGE: 1 of 2 customer rows ahead of 2026-10-06 are in the research queue; 1 are NOT" in p.stdout
    j = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert [x["name"] for x in j["not_in_queue"]] == ["Out"] and (out / "coverage.md").read_text(encoding="utf-8").startswith("# Customer coverage")
    assert [r["conference"] for r in csv.DictReader(open(prop, encoding="utf-8"))] == ["Out"]
