"""The weekly release gate (ACT-68): every check, the verdict, the email and the operator-only rule - on a small world built in a temp folder.

The world: two live conference markets and the awards market (approved files with signed promotion manifests, input lists, raw research, identity files), the four customer sheets (snapshots), a
database with the customer conference rows, last week's published page, this week's two built pages and a manifest. `world()` returns a healthy one; each test breaks exactly one thing.
Nothing here reads a live file, sends mail or touches the network."""
from __future__ import annotations

import csv
import json
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts import release_gate as rg                                     # noqa: E402
from src.cfp_monitor import publish_guard                                   # noqa: E402

ON = date(2026, 10, 12)
NOW = datetime(2026, 10, 12, 7, 30)
COLS = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "SUBMISSION DEADLINE", "STATUS", "Market", "OPPORTUNITY_TYPE", "SOURCE_AS_OF", "EDITION", "STATUS DETAILS",
        "CITY", "STATE_PROVINCE", "COUNTRY", "FORMAT", "GROUNDING_CONFIDENCE", "IS_PROJECTED", "DEADLINE_QUOTE", "ORGANIZER", "TRACK"]


def drow(name, eid, market, op="Speaking", **kw):
    r = {c: "" for c in COLS}
    r.update({"EVENT_ID": eid, "CONFERENCE": name, "Market": market, "OPPORTUNITY_TYPE": op, "STATUS": "Open", "SUBMISSION DEADLINE": "2026-12-01", "SOURCE_AS_OF": "2026-10-10",
              "START DATE": "2027-03-01", "CONFERENCE URL": f"https://{eid}.example.org/", "EDITION": "2027"})
    r.update(kw)
    return r


def write(path: Path, rows, cols=COLS):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def page(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pad = "x" * 25_000
    path.write_text(f"<html><!--{pad}--><script>const DATA = {json.dumps(rows)};\nconst X = 1;</script></html>", encoding="utf-8")


def prow(n, m, op="Speaking", s="Open", dl="2026-12-01", **kw):
    r = {"n": n, "m": m, "op": op, "url": f"https://{n.split()[0].lower()}.example/", "sub": "", "dl": dl, "s": s, "c": "Verified", "chk": "", "st": "Active", "dead": False, "evdead": False,
         "urldead": False, "spon": False, "lq": "", "prov": False}
    r.update(kw)
    return r


class World:
    pass


def world(tmp_path: Path, awards_input_extra=(), snapshot_age_days=0.5, prev_rows=2, cur_rows=2) -> World:
    w = World()
    md = w.md = tmp_path / "Markets"
    snaps = w.snaps = md / "customer_snapshots"
    weekly = w.weekly = tmp_path / "weekly"
    w.db = tmp_path / "data" / "cfp_monitor.db"
    w.qa = tmp_path / "qa"
    # approved files + signed manifests promoted on 2026-10-10 (two days old)
    prom = datetime(2026, 10, 10, 12, 0)
    w.cyber = [drow("Alpha Conf 2027", "2027-alpha", "Cybersecurity"), drow("Beta Conf 2027", "2027-beta", "Cybersecurity")]
    w.util = [drow("Gamma Conf 2027", "2027-gamma", "Utility"), drow("Delta Conf 2027", "2027-delta", "Utility")]
    w.awards = [drow("Epsilon Awards", "2027-eps", "Utility", "Awards", **{"SUBMISSION URL": "https://eps.example/awards/e"}),
                drow("Zeta Awards", "2027-zeta", "Cybersecurity", "Awards", **{"SUBMISSION URL": "https://zeta.example/awards/z"})]
    for name, rows in (("Cybersecurity", w.cyber), ("Utility", w.util), ("Awards", w.awards)):
        p = md / f"{name}_audited.final.csv"
        write(p, rows)
        publish_guard.write_manifest(p, name, "src", "acc.json", "ACCEPTED", promoted_at=prom)
        write(md / f"{name}_input.csv", [{"CONFERENCE": r["CONFERENCE"], "EVENT_ID_CANON": r["EVENT_ID"], "CONFERENCE URL": r["CONFERENCE URL"], "SUBMISSION URL": r["SUBMISSION URL"], "START DATE": r["START DATE"],
                                         "Market": r["Market"], "DUP_OF": ""} for r in rows] + (list(awards_input_extra) if name == "Awards" else []),
              ["CONFERENCE", "EVENT_ID_CANON", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "Market", "DUP_OF"])
    # customer sheets: awards snapshots (the two awards the pages carry) and conference snapshots (only their freshness is read from files)
    stamp = (NOW - timedelta(days=snapshot_age_days)).strftime("%Y%m%d-%H%M%S")
    for client in ("arnica", "utility", "arnica-awards", "utility-awards"):
        folder = snaps / client
        folder.mkdir(parents=True, exist_ok=True)
        if client.endswith("awards"):
            mine = "Zeta Awards,,,,,,https://zeta.example/awards/z" if client == "arnica-awards" else "Epsilon Awards,,,,,,https://eps.example/awards/e"
            (folder / f"{client}_{stamp}.csv").write_text("AWARD,LOCATION,EVENT DATE,SUBMISSION DEADLINE,STATUS,PRIORITY,SUBMISSION URL\n" + mine + "\n", encoding="utf-8")
        else:
            (folder / f"{client}_{stamp}.csv").write_text("CONFERENCE\nx\n", encoding="utf-8")
    # database: the customer conference rows
    w.db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(w.db)
    con.execute("create table client_conferences (client_key text, their_name text, event_id text, their_url text, status text, location text, event_start_date text, withdrawn_by_customer integer, their_deadline text)")
    for key, name, eid, market in (("arnica", "Alpha Conf 2027", "2027-alpha", "Cybersecurity"), ("arnica", "Beta Conf 2027", "2027-beta", "Cybersecurity"),
                                   ("utility-global", "Gamma Conf 2027", "2027-gamma", "Utility"), ("utility-global", "Delta Conf 2027", "2027-delta", "Utility")):
        con.execute("insert into client_conferences values (?,?,?,?,?,?,?,?,?)", (key, name, eid, f"https://{eid}.example.org/", "", "", "2027-03-01", 0, ""))
    con.commit()
    con.close()
    # pages: last week's and this week's; manifest
    page(weekly / "2026-10-05" / "Conference Review 2026-10-05 - Live Markets.html", [prow(f"Row{i} Conf", "Cybersecurity") for i in range(prev_rows)])
    page(weekly / "2026-10-05" / "Awards Review 2026-10-05.html", [prow("Epsilon Awards", "Utility", "Awards"), prow("Zeta Awards", "Cybersecurity", "Awards")])
    for folder in (weekly / "2026-10-12", weekly / "work_2026-10-12"):
        page(folder / "Conference Review 2026-10-12 - Live Markets.html", [prow(f"Row{i} Conf", "Cybersecurity") for i in range(cur_rows)])
        page(folder / "Awards Review 2026-10-12.html", [prow("Epsilon Awards", "Utility", "Awards", sub="https://eps.example/awards/e"), prow("Zeta Awards", "Cybersecurity", "Awards", sub="https://zeta.example/awards/z")])
    (weekly / "work_2026-10-12" / "MANIFEST.md").write_text("# Weekly\n\n    HEALTH: HEALTHY\n", encoding="utf-8")
    w.commit = tmp_path / "commitments.csv"
    w.commit.write_text("id,promised_on,note,market,event_id,column,op,expected,due,what\n", encoding="utf-8")
    w.given = tmp_path / "given_ids.csv"
    w.given.write_text("event_id,market,given_on,source\n", encoding="utf-8")
    w.ledger = tmp_path / "ledger.csv"
    w.ledger.write_text("event_name,url,client,reason,ruled_by,ruled_on\n", encoding="utf-8")
    return w


def opts(w: World, preflight=False) -> rg.Opts:
    return rg.Opts(ON, NOW, preflight, w.md, w.db, w.snaps, None, w.weekly, None, w.qa, w.commit, w.given, w.ledger)


def run(w: World, preflight=False) -> dict:
    return rg.evaluate(opts(w, preflight))


def status(rep, cid):
    return next(c for c in rep["checks"] if c["id"] == cid)["status"]


# ------------------------------------------------------------------ verdict
def test_a_healthy_world_is_GO():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        rep = run(world(Path(d)))
        assert rep["verdict"] == "GO", [(c["id"], c["status"], c["summary"]) for c in rep["checks"] if c["status"] != "PASS"]


def test_verdict_function():
    C = rg.Check
    assert rg.verdict_of([C("a", "t", "PASS", ""), C("b", "t", "NA", "")]) == "GO"
    assert rg.verdict_of([C("a", "t", "PASS", ""), C("b", "t", "WARN", "")]) == "GO WITH NOTES"
    assert rg.verdict_of([C("a", "t", "WARN", ""), C("b", "t", "FAIL", "")]) == "NO-GO"


def test_a_check_that_cannot_run_is_a_warning_never_a_silent_pass():
    c = rg.safely("x", "title", lambda: 1 / 0)
    assert c["status"] == "WARN" and "could not be judged" in c["summary"]


# ------------------------------------------------------------------ (a) pages
def test_a_page_missing_or_unpublished_is_NO_GO(tmp_path):
    w = world(tmp_path)
    (w.weekly / "2026-10-12" / "Awards Review 2026-10-12.html").unlink()
    rep = run(w)
    assert status(rep, "a") == "FAIL" and rep["verdict"] == "NO-GO"


def test_a_degraded_manifest_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    (w.weekly / "work_2026-10-12" / "MANIFEST.md").write_text("    HEALTH: DEGRADED\n", encoding="utf-8")
    assert status(run(w), "a") == "FAIL"


def test_a_stale_approved_file_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    publish_guard.write_manifest(w.md / "Awards_audited.final.csv", "Awards", "src", "acc.json", "ACCEPTED", promoted_at=datetime(2026, 10, 1))
    rep = run(w)
    assert status(rep, "a") == "FAIL" and any("Awards approved file" in r for c in rep["checks"] if c["id"] == "a" for r in c["rows"])


def test_an_old_page_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    rep = rg.evaluate(rg.Opts(date(2026, 10, 13), NOW, False, w.md, w.db, w.snaps, None, w.weekly, w.weekly / "work_2026-10-12", w.qa, w.commit, w.given, w.ledger))
    assert status(rep, "a") == "FAIL"


# ------------------------------------------------------------------ (b) coverage
def test_a_customer_award_that_is_not_in_the_research_queue_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    (w.snaps / "arnica-awards" / sorted(p.name for p in (w.snaps / "arnica-awards").iterdir())[0]).write_text(
        "AWARD,SUBMISSION URL\nZeta Awards,https://zeta.example/awards/z\nBrand New Prize,https://new.example/prize/x\n", encoding="utf-8")
    rep = run(w)
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert b["status"] == "FAIL" and any("Brand New Prize" in r and "NOT in the research queue" in r for r in b["rows"])
    assert rep["verdict"] == "NO-GO"


def test_an_award_in_the_queue_but_not_researched_is_named_with_the_reason_awaiting_first_research(tmp_path):
    extra = [{"CONFERENCE": "Queued Prize", "EVENT_ID_CANON": "", "CONFERENCE URL": "", "SUBMISSION URL": "https://q.example/prize/q", "START DATE": "", "Market": "Cybersecurity", "DUP_OF": ""}]
    w = world(tmp_path, awards_input_extra=extra)
    f = next((w.snaps / "arnica-awards").iterdir())
    f.write_text("AWARD,SUBMISSION URL\nZeta Awards,https://zeta.example/awards/z\nQueued Prize,https://q.example/prize/q\n", encoding="utf-8")
    rep = run(w)
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert b["status"] == "WARN" and any("Queued Prize" in r and rg.R_QUEUED in r for r in b["rows"])


def test_a_researched_award_without_an_id_is_named_as_waiting_for_an_id(tmp_path):
    extra = [{"CONFERENCE": "Researched Prize", "EVENT_ID_CANON": "", "CONFERENCE URL": "", "SUBMISSION URL": "https://r.example/prize/r", "START DATE": "", "Market": "Cybersecurity", "DUP_OF": ""}]
    w = world(tmp_path, awards_input_extra=extra)
    next((w.snaps / "arnica-awards").iterdir()).write_text("AWARD,SUBMISSION URL\nZeta Awards,https://zeta.example/awards/z\nResearched Prize,https://r.example/prize/r\n", encoding="utf-8")
    # the Friday research answered it (raw row + identity row), the approved file does not carry it, the customer is not shown it
    write(w.md / "Awards_audited.csv", [drow("Researched Prize", "2027-rp", "Cybersecurity", "Awards", **{"SUBMISSION URL": "https://r.example/prize/r"})])
    write(w.md / "Awards_audited.identity.csv", [{"OUTPUT_EVENT_ID": "2027-rp", "OUTPUT_CONFERENCE": "Researched Prize", "INPUT_CONFERENCE": "Researched Prize", "EVENT_ID_CANON": ""}],
          ["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"])
    rep = run(w)
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert any("Researched Prize" in r and rg.R_ID in r for r in b["rows"])


def test_every_reason_used_is_in_the_fixed_vocabulary(tmp_path):
    w = world(tmp_path)
    rep = run(w)
    for cov in rep["coverage"].values():
        assert "error" not in cov
        for st in cov.values():
            for m in st["missing"]:
                assert m["reason"] in rg.REASONS
    assert len(rg.REASONS) == len(set(rg.REASONS))


def test_a_past_awards_row_is_counted_with_the_reason_past_event(tmp_path):
    w = world(tmp_path)
    next((w.snaps / "utility-awards").iterdir()).write_text("AWARD,EVENT DATE,SUBMISSION URL\nEpsilon Awards,,https://eps.example/awards/e\nOld Gala,04/15/2020,https://o.example/gala/o\n", encoding="utf-8")
    rep = run(w)
    st = rep["coverage"]["awards"]["utility-awards"]
    assert any(m["name"] == "Old Gala" and m["reason"] == rg.R_PAST for m in st["missing"]) and st["past"] == 1
    assert status(rep, "b") != "FAIL", "a past event that is not on the research list is not a gap"


def test_a_conference_customer_row_not_on_any_list_is_a_FAIL_and_a_held_one_is_named(tmp_path):
    w = world(tmp_path)
    con = sqlite3.connect(w.db)
    con.execute("insert into client_conferences values ('arnica','Lost Summit 2027','', 'https://lost.example.org/','','', '2027-05-01',0,'')")
    con.execute("insert into client_conferences values ('arnica','Held Summit 2027','2027-held', 'https://held.example.org/','','', '2027-06-01',0,'')")
    con.commit()
    con.close()
    # Held Summit is on the research list with an id but is not in the approved file
    inp = w.md / "Cybersecurity_input.csv"
    rows = list(csv.DictReader(open(inp, encoding="utf-8", newline="")))
    rows.append({"CONFERENCE": "Held Summit 2027", "EVENT_ID_CANON": "2027-held", "CONFERENCE URL": "https://held.example.org/", "SUBMISSION URL": "", "START DATE": "2027-06-01", "Market": "Cybersecurity", "DUP_OF": ""})
    write(inp, rows, ["CONFERENCE", "EVENT_ID_CANON", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "Market", "DUP_OF"])
    rep = run(w)
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert b["status"] == "FAIL"
    assert any("Lost Summit 2027" in r and "NOT in the research queue" in r for r in b["rows"])
    assert any("Held Summit 2027" in r and rg.R_QUEUED in r for r in b["rows"]), "queued, never researched: awaiting first research"


def test_past_and_withdrawn_conference_rows_are_not_gaps(tmp_path):
    w = world(tmp_path)
    con = sqlite3.connect(w.db)
    con.execute("insert into client_conferences values ('arnica','Old Summit 2025','', 'https://old.example.org/','','', '2025-05-01',0,'')")
    con.execute("insert into client_conferences values ('arnica','Dropped Summit 2027','', 'https://dropped.example.org/','','', '2027-05-01',1,'')")
    con.commit()
    con.close()
    st = run(w)["coverage"]["conference"]["arnica"]
    reasons = {m["name"]: m["reason"] for m in st["missing"]}
    assert reasons == {"Old Summit 2025": rg.R_PAST, "Dropped Summit 2027": rg.R_WITHDRAWN}


def test_gate_reasons_are_read_from_the_import_log():
    log = ("  [FAIL] 4    No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)  (2)\n"
           "           - CDAO Fall: The event is confirmed for October 26-27, 2026\n"
           "[Cybersecurity] NEW EVENT HELD (not loaded): Some Award - waiting for an id\n")
    got = rg.gate_reasons_from_log(log)
    assert got and got[0][0] == "CDAO Fall" and "No active-call prose" in got[0][1]
    look = {"log": got, "held_rows": {"perm-1": "held back by the row rule"}}
    assert "No active-call prose" in rg.held_reason("CDAO Fall", "", look)
    assert rg.held_reason("Anything", "perm-1", look) == "held back by the row rule"
    assert rg.held_reason("Unknown", "", look) == ""


# ------------------------------------------------------------------ (c) (e)
def test_provisional_and_researched_but_not_on_page_rows_are_counted_and_named(tmp_path):
    w = world(tmp_path)
    write(w.md / "Awards_audited.csv", [drow("Brand New Prize", "2027-bnp", "Cybersecurity", "Awards", **{"SUBMISSION URL": "https://b.example/prize/b"}),
                                         drow("A Speaking Thing", "2027-st", "Cybersecurity", "Speaking")])
    write(w.md / "Awards_audited.identity.csv", [{"OUTPUT_EVENT_ID": "2027-bnp", "OUTPUT_CONFERENCE": "Brand New Prize", "INPUT_CONFERENCE": "Brand New Prize", "EVENT_ID_CANON": ""},
                                                 {"OUTPUT_EVENT_ID": "2027-st", "OUTPUT_CONFERENCE": "A Speaking Thing", "INPUT_CONFERENCE": "A Speaking Thing", "EVENT_ID_CANON": ""}],
          ["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"])
    # the lookup needs award ids in the database
    con = sqlite3.connect(w.db)
    con.execute("create table award_grounding_facts (event_id text, upstream_event_id text)")
    con.execute("insert into award_grounding_facts values ('perm-eps','2027-eps')")
    con.commit()
    con.close()
    # the built page shows the provisional row
    page(w.weekly / "2026-10-12" / "Awards Review 2026-10-12.html", [prow("Epsilon Awards", "Utility", "Awards", sub="https://eps.example/awards/e"), prow("Zeta Awards", "Cybersecurity", "Awards", sub="https://zeta.example/awards/z"),
                                                                    prow("Brand New Prize", "Cybersecurity", "Awards", prov=True, c="")])
    rep = run(w)
    e = next(c for c in rep["checks"] if c["id"] == "e")
    assert e["status"] == "WARN" and any("Brand New Prize" in r for r in e["rows"])
    c = next(c for c in rep["checks"] if c["id"] == "c")
    assert any("A Speaking Thing" in r and "left off the page on purpose" in r for r in c["rows"]), "a true non-award nobody lists is named as left off, not lost"
    assert rep["counts"]["provisional"] == 1


# ------------------------------------------------------------------ (d) (f)
def test_stale_rows_are_named(tmp_path):
    w = world(tmp_path)
    rows = w.cyber + [drow("Ancient Conf 2027", "2027-ancient", "Cybersecurity", **{"SOURCE_AS_OF": "2026-06-01"})]
    p = w.md / "Cybersecurity_audited.final.csv"
    write(p, rows)
    publish_guard.write_manifest(p, "Cybersecurity", "src", "acc.json", "ACCEPTED", promoted_at=datetime(2026, 10, 10, 12, 0))
    d = next(c for c in run(w)["checks"] if c["id"] == "d")
    assert d["status"] == "WARN" and any("Ancient Conf 2027" in r for r in d["rows"]) and not any("Alpha" in r for r in d["rows"])


@pytest.mark.parametrize("age,expect", [(0.5, "PASS"), (2.5, "WARN"), (4.5, "FAIL")])
def test_snapshot_freshness(tmp_path, age, expect):
    w = world(tmp_path, snapshot_age_days=age)
    assert status(run(w), "f") == expect


def test_a_missing_snapshot_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    for p in (w.snaps / "utility").iterdir():
        p.unlink()
    assert status(run(w), "f") == "FAIL"


# ------------------------------------------------------------------ (g) build QA
def test_an_open_row_past_its_deadline_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    page(w.weekly / "2026-10-12" / "Conference Review 2026-10-12 - Live Markets.html", [prow("Row0 Conf", "Cybersecurity", s="Open", dl="2026-10-01"), prow("Row1 Conf", "Cybersecurity")])
    g = next(c for c in run(w)["checks"] if c["id"] == "g")
    assert g["status"] == "FAIL" and any("Row0 Conf" in r for r in g["rows"])


def test_a_retired_label_is_a_FAIL(tmp_path):
    w = world(tmp_path)
    page(w.weekly / "2026-10-12" / "Conference Review 2026-10-12 - Live Markets.html", [prow("Row0 Conf", "Cybersecurity", op="Registration"), prow("Row1 Conf", "Cybersecurity")])
    g = next(c for c in run(w)["checks"] if c["id"] == "g")
    assert g["status"] == "FAIL" and any("retired" in r for r in g["rows"])


def test_a_page_more_than_10_percent_smaller_than_last_week_is_a_FAIL(tmp_path):
    w = world(tmp_path, prev_rows=20, cur_rows=17)
    g = next(c for c in run(w)["checks"] if c["id"] == "g")
    assert g["status"] == "FAIL" and any("percent fewer" in r for r in g["rows"])
    w2 = world(tmp_path / "ok", prev_rows=20, cur_rows=19)
    assert not any("percent fewer" in r for c in run(w2)["checks"] if c["id"] == "g" for r in c["rows"])


def test_a_disputed_deadline_is_a_WARN_not_a_FAIL(tmp_path):
    w = world(tmp_path)
    page(w.weekly / "2026-10-12" / "Conference Review 2026-10-12 - Live Markets.html", [prow("Row0 Conf", "Cybersecurity", chk="contradicted"), prow("Row1 Conf", "Cybersecurity")])
    g = next(c for c in run(w)["checks"] if c["id"] == "g")
    assert g["status"] == "WARN" and any("DISPUTES" in r for r in g["rows"])


# ------------------------------------------------------------------ (h) upstream
def test_an_overdue_promise_and_an_id_owed_are_WARNs(tmp_path):
    w = world(tmp_path)
    w.commit.write_text("id,promised_on,note,market,event_id,column,op,expected,due,what\nC01,2026-10-01,9,Cybersecurity,2027-alpha,STATUS,equals,Closed,2026-10-10,Alpha must be Closed\n", encoding="utf-8")
    inp = w.md / "Awards_input.csv"
    rows = list(csv.DictReader(open(inp, encoding="utf-8", newline="")))
    rows.append({"CONFERENCE": "Owed Prize", "EVENT_ID_CANON": "", "CONFERENCE URL": "", "SUBMISSION URL": "", "START DATE": "", "Market": "Utility", "DUP_OF": ""})
    write(inp, rows, ["CONFERENCE", "EVENT_ID_CANON", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "Market", "DUP_OF"])
    h = next(c for c in run(w)["checks"] if c["id"] == "h")
    assert h["status"] == "WARN" and any("C01" in r for r in h["rows"]) and any("Owed Prize" in r for r in h["rows"])


# ------------------------------------------------------------------ pre-flight
def test_preflight_builds_no_pages_and_says_so(tmp_path):
    w = world(tmp_path)
    for f in (w.weekly / "2026-10-12", w.weekly / "work_2026-10-12"):
        for p in f.glob("*.html"):
            p.unlink()
    rep = run(w, preflight=True)
    assert rep["pages"]["conference"] is None and rep["preflight"] is True
    a = next(c for c in rep["checks"] if c["id"] == "a")
    assert a["status"] == "PASS" and "not built yet" in a["summary"]
    subj, text, _h = rg.build_email(rep)
    assert subj.startswith("CFP weekly pre-flight:") and "Sunday pre-flight" in text
    assert rep["counts"]["conference"] == 4 and rep["counts"]["awards"] == 2


# ------------------------------------------------------------------ email
def test_the_email_subject_and_body(tmp_path):
    w = world(tmp_path)
    rep = run(w)
    subj, text, html_ = rg.build_email(rep)
    assert subj == f"CFP weekly pages: {rep['verdict']} - Conferences 2, Awards 2"
    assert text.startswith("VERDICT:") and "CUSTOMER COVERAGE" in text and "Arnica conferences" in text and html_.startswith("<html>")
    assert text.isascii()
    assert len([ln for ln in text.splitlines() if ln.startswith("- ")]) <= 10


class Stub:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, subject, body, html=None, to_env="CFP_ALERT_TO", attachments=None, **kw):
        self.calls.append({"subject": subject, "body": body, "html": html, "to_env": to_env, "attachments": attachments, "kw": kw})
        return self.ok


def test_the_email_goes_to_the_operator_variable_only_with_both_pages_attached(tmp_path):
    w = world(tmp_path)
    rep = run(w)
    stub = Stub()
    assert rg.send(rep, stub) is True
    (call,) = stub.calls
    assert call["to_env"] == "CFP_RECAP_TO" and not call["kw"], "no recipient can be named: only the operator variable"
    assert sorted(Path(p).name for p in call["attachments"]) == ["Awards Review 2026-10-12.html", "Conference Review 2026-10-12 - Live Markets.html"]
    import inspect
    assert "to" not in inspect.signature(rg.send).parameters and "recipient" not in inspect.signature(rg.send).parameters


def test_a_page_over_the_size_limit_is_not_attached(tmp_path, monkeypatch):
    w = world(tmp_path)
    rep = run(w)
    monkeypatch.setattr(rg, "MAX_ATTACH_BYTES", 10)
    assert rg.attachments_for(rep) == []


def test_the_real_mailer_accepts_attachments_and_names_the_operator_variable(tmp_path, monkeypatch):
    """alerts.maybe_send_email: multipart/mixed with the files, recipient only from CFP_RECAP_TO. smtplib is replaced; nothing leaves the machine."""
    from src.cfp_monitor import alerts
    sent = []

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def sendmail(self, frm, to, msg):
            sent.append((frm, to, msg))
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k, v in {"CFP_SMTP_HOST": "h", "CFP_SMTP_USER": "u@x", "CFP_SMTP_PASS": "p", "CFP_RECAP_TO": "operator@example.org", "CFP_ALERT_TO": "someone-else@example.org"}.items():
        monkeypatch.setenv(k, v)
    f = tmp_path / "Page One.html"
    f.write_text("<html>hello</html>", encoding="utf-8")
    assert alerts.maybe_send_email("s", "b", html="<p>b</p>", to_env="CFP_RECAP_TO", attachments=[f]) is True
    frm, to, msg = sent[0]
    assert to == ["operator@example.org"] and "multipart/mixed" in msg and 'filename="Page One.html"' in msg


# ------------------------------------------------------------------ main never blocks
def test_main_dry_run_writes_the_report_and_sends_nothing(tmp_path, capsys, monkeypatch):
    w = world(tmp_path)
    boom = Stub()
    monkeypatch.setattr("src.cfp_monitor.alerts.maybe_send_email", boom)
    rc = rg.main(["--on", "2026-10-12", "--now", NOW.isoformat(), "--dry-run", "--markets-dir", str(w.md), "--db", str(w.db), "--snapshots-dir", str(w.snaps), "--weekly-dir", str(w.weekly),
                  "--qa-root", str(w.qa)])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("GATE:") and not boom.calls
    d = w.qa / "2026-10-12"
    assert (d / "release_gate.md").exists() and (d / "release_gate.json").exists() and (d / "release_gate_email.txt").exists()
    js = json.loads((d / "release_gate.json").read_text(encoding="utf-8"))
    assert js["step"] == "release_gate" and js["verdict"] in ("GO", "GO WITH NOTES", "NO-GO") and js["email"]["subject"].startswith("CFP weekly pages:")


def test_main_exits_zero_even_when_everything_is_missing(tmp_path, capsys):
    rc = rg.main(["--on", "2026-10-12", "--dry-run", "--markets-dir", str(tmp_path / "nothing"), "--db", str(tmp_path / "no.db"), "--snapshots-dir", str(tmp_path / "nosnaps"),
                  "--weekly-dir", str(tmp_path / "noweekly"), "--qa-root", str(tmp_path / "qa")])
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("GATE:")
    rc = rg.main(["--on", "not-a-date"])
    assert rc == 0 and "GATE: UNKNOWN" in capsys.readouterr().out


def test_preflight_writes_its_own_report_beside_the_monday_one(tmp_path, capsys):
    w = world(tmp_path)
    common = ["--on", "2026-10-12", "--now", NOW.isoformat(), "--dry-run", "--markets-dir", str(w.md), "--db", str(w.db), "--snapshots-dir", str(w.snaps), "--weekly-dir", str(w.weekly), "--qa-root", str(w.qa)]
    rg.main(common)
    rg.main(common + ["--preflight"])
    d = w.qa / "2026-10-12"
    assert (d / "release_gate.json").exists() and (d / "preflight.json").exists()
