"""ACT-46 and ACT-47: scripts/approved_edit.py, scripts/withdraw_citations.py and scripts/retire_duplicates.py on temporary approved files and a temporary database. No network."""
import csv
import sqlite3
import sys
from pathlib import Path

import pytest

from scripts import approved_edit as AE
from scripts import retire_duplicates as RD
from scripts import withdraw_citations as WC

COLS = ["EVENT_ID", "CONFERENCE", "EDITION", "START DATE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED", "GROUNDING_CONFIDENCE", "STATUS"]


def _row(i, name, **k):
    base = {"EVENT_ID": f"up-{i}", "CONFERENCE": name, "EDITION": "2026", "START DATE": "2026-06-01", "SUBMISSION DEADLINE": "2026-02-01", "DEADLINE_EVIDENCE_URL": f"https://x{i}.example/cfp",
            "DEADLINE_QUOTE": "CFP closes February 1", "IS_PROJECTED": "false", "GROUNDING_CONFIDENCE": "Verified (2026)", "STATUS": "Closed"}
    base.update(k)
    return base


def _write(path, rows, bom=False, crlf=True):
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(rows)


def _world(tmp_path):
    """markets dir with both approved files, a data root with the database and seeds."""
    mk, data = tmp_path / "markets", tmp_path / "data"
    (data / "market_sheets").mkdir(parents=True)
    mk.mkdir()
    _write(mk / "Cybersecurity_audited.final.csv", [_row(1, "Alpha Con 2026"), _row(2, "Beta Summit 2026"), _row(3, "Gamma Expo 2026", **{"DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": ""})])
    _write(mk / "Utility_audited.final.csv", [_row(4, "Delta Forum 2026")])
    with open(data / "market_sheets" / "cyber_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "EVENT_ID_CANON", "CONFERENCE"])
        w.writeheader()
        for i in (1, 2, 3, 4):
            w.writerow({"EVENT_ID": f"up-{i}", "EVENT_ID_CANON": f"2026-c{i}", "CONFERENCE": f"n{i}"})
    db = data / "cfp_monitor.db"
    c = sqlite3.connect(db)
    c.execute("create table grounding_facts (event_id, name, url, status, edition, start_date, deadline_evidence_url, deadline_quote, is_projected)")
    c.execute("create table link_checks (url, state)")
    c.execute("create table client_conferences (event_id, status)")
    for i, n in ((1, "Alpha Con 2026"), (2, "Beta Summit 2026"), (3, "Gamma Expo 2026"), (4, "Delta Forum 2026")):
        c.execute("insert into grounding_facts values (?,?,?,?,?,?,?,?,?)", (f"2026-c{i}", n, f"https://x{i}.example/", "Closed", "2026", "2026-06-01", f"https://x{i}.example/cfp" if i != 3 else "", "CFP closes February 1" if i != 3 else "", "false"))
    c.execute("insert into grounding_facts values ('2026-dupe-of-1','Alpha Con (old name)','https://x1.example/','Closed','2026','2026-06-01','','','true')")
    c.execute("insert into link_checks values ('https://x1.example/cfp','dead'), ('https://x2.example/cfp','alive'), ('https://x4.example/cfp','dead')")
    c.execute("insert into client_conferences values ('2026-dupe-of-1','Submitted')")
    c.commit()
    c.close()
    return mk, data, db


def test_a_cell_edit_is_proved_and_backed_up_and_keeps_bom_and_line_endings(tmp_path):
    p = tmp_path / "f.csv"
    _write(p, [_row(1, "A"), _row(2, "B")], bom=True, crlf=True)
    cols, rows, bom, crlf = AE.read_approved(p)
    assert bom and crlf
    after = [dict(r) for r in rows]
    after[1]["STATUS"] = "Open"
    bak = AE.write_approved(p, cols, rows, after, bom, crlf, "t", expect_cells={(1, "STATUS")})
    assert bak.exists() and bak.read_bytes() != p.read_bytes()
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw
    assert AE.read_approved(p)[1][1]["STATUS"] == "Open"


def test_an_unexpected_change_raises_and_leaves_the_original_in_place(tmp_path):
    p = tmp_path / "f.csv"
    _write(p, [_row(1, "A"), _row(2, "B")])
    cols, rows, bom, crlf = AE.read_approved(p)
    after = [dict(r) for r in rows]
    after[0]["STATUS"] = "Open"
    after[1]["CONFERENCE"] = "B changed too"
    original = p.read_bytes()
    with pytest.raises(AssertionError):
        AE.write_approved(p, cols, rows, after, bom, crlf, "t", expect_cells={(0, "STATUS")})
    assert p.read_bytes() == original and not p.with_name(p.name + ".tmp").exists()


def test_a_row_removal_must_remove_exactly_the_named_row(tmp_path):
    p = tmp_path / "f.csv"
    _write(p, [_row(1, "A"), _row(2, "B"), _row(3, "C")])
    cols, rows, bom, crlf = AE.read_approved(p)
    AE.write_approved(p, cols, rows, [rows[0], rows[2]], bom, crlf, "t", expect_removed={1})
    assert [r["CONFERENCE"] for r in AE.read_approved(p)[1]] == ["A", "C"]
    cols, rows, bom, crlf = AE.read_approved(p)
    with pytest.raises(AssertionError):
        AE.write_approved(p, cols, rows, [rows[1]], bom, crlf, "t", expect_removed={1})            # that would drop row 0 instead of row 1... the proof refuses
    with pytest.raises(ValueError):
        AE.write_approved(p, cols, rows, rows, bom, crlf, "t")                                       # neither expectation given


def test_database_backup_is_a_consistent_copy(tmp_path):
    mk, data, db = _world(tmp_path)
    bak = AE.backup_db(db, "t")
    c = sqlite3.connect(bak)
    assert c.execute("select count(*) from grounding_facts").fetchone()[0] == 5


# ----------------------------------------------------------------------------------------------- ACT-46
def _decl(tmp_path, ids, extra=None):
    p = tmp_path / "w.csv"
    cols = ["EVENT_ID", "reason"] + (extra or [])
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i in ids:
            w.writerow({"EVENT_ID": i, "reason": "upstream withdrew"})
    return p


def test_a_withdrawal_file_may_not_carry_anything_but_an_id_a_reason_and_blank_citations(tmp_path):
    with pytest.raises(SystemExit):
        WC.read_declaration(_decl(tmp_path, ["2026-c1"], extra=["SUBMISSION DEADLINE"]))
    p = tmp_path / "x.csv"
    p.write_text("EVENT_ID,DEADLINE_QUOTE\n2026-c1,a new quote\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        WC.read_declaration(p)                                                                       # a withdrawal declares a clear, it carries no new citation
    p.write_text("event,reason\nx,y\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        WC.read_declaration(p)                                                                       # no EVENT_ID (OUR id) column


def test_plan_clears_the_citation_keeps_the_deadline_and_projects_it_but_refuses_a_live_page():
    row = _row(1, "A")
    pl = WC.plan_row(row, {"deadline_evidence_url": "u", "deadline_quote": "q", "is_projected": "false"}, "dead", False)
    assert pl["file"] == {"DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": "", "IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "Projected (2026)"} and "SUBMISSION DEADLINE" not in pl["file"]
    assert pl["db"] == {"deadline_evidence_url": "", "deadline_quote": "", "is_projected": "true"}
    assert "ALIVE" in WC.plan_row(row, None, "alive", False)["skip"] and WC.plan_row(row, None, "alive", True)["skip"] == ""
    assert WC.plan_row(_row(3, "G", **{"DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": ""}), {"deadline_evidence_url": "", "deadline_quote": ""}, "none", False)["skip"] == "already clear in both"
    assert "no row" in WC.plan_row(None, None, "none", False)["skip"]
    already = WC.plan_row(_row(1, "A", IS_PROJECTED="true", GROUNDING_CONFIDENCE="Projected (2026)"), None, "dead", False)
    assert "IS_PROJECTED" not in already["file"] and "GROUNDING_CONFIDENCE" not in already["file"]


def _run(mod, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x"] + argv)
    return mod.main()


def test_withdraw_end_to_end_changes_only_the_named_cells_and_the_database_row_and_writes_the_ledger(tmp_path, monkeypatch):
    mk, data, db = _world(tmp_path)
    decl = _decl(tmp_path, ["2026-c1", "2026-c2", "2026-c3", "2026-nope"])
    ledger = tmp_path / "ledger.csv"
    args = ["--file", str(decl), "--source", "upstream note 28", "--markets-dir", str(mk), "--db", str(db), "--ledger", str(ledger), "--today", "2026-10-05"]
    before = (mk / "Cybersecurity_audited.final.csv").read_bytes()
    assert _run(WC, args, monkeypatch) == 0
    assert (mk / "Cybersecurity_audited.final.csv").read_bytes() == before and not ledger.exists()   # report only
    assert _run(WC, args + ["--apply"], monkeypatch) == 0
    cols, rows, bom, crlf = AE.read_approved(mk / "Cybersecurity_audited.final.csv")
    r1, r2, r3 = rows
    assert (r1["DEADLINE_EVIDENCE_URL"], r1["DEADLINE_QUOTE"], r1["IS_PROJECTED"], r1["GROUNDING_CONFIDENCE"]) == ("", "", "true", "Projected (2026)") and r1["SUBMISSION DEADLINE"] == "2026-02-01"
    assert r2["DEADLINE_EVIDENCE_URL"] == "https://x2.example/cfp"                                       # c2's page is ALIVE: refused, untouched
    assert r3 == _row(3, "Gamma Expo 2026", **{"DEADLINE_EVIDENCE_URL": "", "DEADLINE_QUOTE": ""}) | {}  # already clear: untouched
    c = sqlite3.connect(db)
    assert c.execute("select deadline_evidence_url, deadline_quote, is_projected from grounding_facts where event_id='2026-c1'").fetchone() == ("", "", "true")
    assert c.execute("select deadline_evidence_url from grounding_facts where event_id='2026-c2'").fetchone()[0] == "https://x2.example/cfp"
    led = list(csv.DictReader(open(ledger, encoding="utf-8")))
    assert [r["event_id"] for r in led] == ["2026-c1"] and led[0]["old_url"] == "https://x1.example/cfp" and led[0]["source"] == "upstream note 28" and led[0]["link_state"] == "dead"
    assert list(mk.glob("Cybersecurity_audited.final.pre-withdraw-*.bak.csv")) and list(data.glob("cfp_monitor.pre-withdraw-*.db"))
    assert not list(mk.glob("Utility_audited.final.pre-withdraw-*"))                                      # an untouched file gets no backup


def test_propose_lists_dead_citations_of_calls_that_are_over(tmp_path, monkeypatch, capsys):
    mk, data, db = _world(tmp_path)
    out = tmp_path / "p.csv"
    assert _run(WC, ["--propose", "--out", str(out), "--markets-dir", str(mk), "--db", str(db), "--today", "2026-10-05"], monkeypatch) == 0
    ids = [r["EVENT_ID"] for r in csv.DictReader(open(out, encoding="utf-8"))]
    assert sorted(ids) == ["2026-c1", "2026-c4"]                                                          # c2 alive, c3 has no citation
    assert _run(WC, ["--propose", "--markets-dir", str(mk), "--db", str(db), "--today", "2026-01-01"], monkeypatch) == 0
    assert "0 row(s) qualify" in capsys.readouterr().out                                                  # nothing has started and no deadline has passed yet
    assert _run(WC, ["--propose", "--out", str(out), "--markets-dir", str(mk), "--db", str(db), "--today", "2026-03-01"], monkeypatch) == 0     # deadlines (2026-02-01) passed, events not started
    assert sorted(r["EVENT_ID"] for r in csv.DictReader(open(out, encoding="utf-8"))) == ["2026-c1", "2026-c4"]


# ----------------------------------------------------------------------------------------------- ACT-47
LEDGER_TEXT = ("# c\n2026-10-05 | 2026-c2 | 2026-c1 | upstream | https://x1.example/ | Alpha Con and the Old Name are one event | same site\n"
               "2026-10-05 | 2026-c1 | 2026-dupe-of-1 | upstream | https://x1.example/ | Alpha Con is held in the Grand Hall | the old name\n")


def test_the_ledger_needs_a_page_and_a_sentence_and_two_different_ids(tmp_path):
    p = tmp_path / "l.txt"
    p.write_text(LEDGER_TEXT, encoding="utf-8")
    d = RD.load_retirements(p)
    assert [x["retired"] for x in d] == ["2026-c1", "2026-dupe-of-1"] and d[0]["page"].startswith("https://")
    for bad in ("2026-10-05 | a | a | w | https://x/ | a long enough sentence here | y\n", "2026-10-05 | a | b | w | not a url | a long enough sentence here | y\n",
                "2026-10-05 | a | b | w | https://x/ | short | y\n", "2026-10-05 | a | b | w | https://x/ | a long enough sentence here\n", "someday | a | b | w | https://x/ | a long enough sentence here | y\n"):
        p.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            RD.load_retirements(p)


def test_the_real_ledger_parses_and_names_four_pairs_with_pages():
    d = RD.load_retirements()
    assert len(d) == 4 and all(x["page"].startswith("https://") and len(x["quote"]) > 30 for x in d)


def test_retire_is_blocked_while_the_survivor_is_not_on_the_published_page(tmp_path, monkeypatch, capsys):
    mk, data, db = _world(tmp_path)
    led = tmp_path / "l.txt"
    led.write_text("2026-10-05 | 2026-dupe-of-1 | 2026-c1 | upstream | https://x1.example/ | Alpha Con and the Old Name are one event | survivor is not on the page\n", encoding="utf-8")
    args = ["--ledger", str(led), "--markets-dir", str(mk), "--db", str(db), "--held-rows", str(tmp_path / "held.txt")]
    assert _run(RD, args, monkeypatch) == 1
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "SURVIVOR" in out and "customer row (Submitted)" not in out
    before = (mk / "Cybersecurity_audited.final.csv").read_bytes()
    assert _run(RD, args + ["--apply"], monkeypatch) == 1 and (mk / "Cybersecurity_audited.final.csv").read_bytes() == before and not (tmp_path / "held.txt").exists()


def test_retire_removes_only_the_retired_row_declares_it_once_and_never_touches_the_database(tmp_path, monkeypatch, capsys):
    mk, data, db = _world(tmp_path)
    led = tmp_path / "l.txt"
    led.write_text("2026-10-05 | 2026-c2 | 2026-c1 | upstream | https://x1.example/ | Alpha Con and the Old Name are one event | same site\n", encoding="utf-8")
    held = tmp_path / "held.txt"
    held.write_text("# header\n2026-aes-x  # an older hold\n", encoding="utf-8")
    args = ["--ledger", str(led), "--markets-dir", str(mk), "--db", str(db), "--held-rows", str(held)]
    db_before = sqlite3.connect(db).execute("select count(*), group_concat(event_id) from grounding_facts").fetchone()
    assert _run(RD, args + ["--apply"], monkeypatch) == 0
    out = capsys.readouterr().out
    assert "on the published page now: survivor yes, retired yes" in out and "read back: 2026-c2: 1 row(s) of this event on the published page" in out     # two rows before, one after
    names = [r["CONFERENCE"] for r in AE.read_approved(mk / "Cybersecurity_audited.final.csv")[1]]
    assert names == ["Beta Summit 2026", "Gamma Expo 2026"]                                                # exactly Alpha (2026-c1) gone, order kept
    assert [r["CONFERENCE"] for r in AE.read_approved(mk / "Utility_audited.final.csv")[1]] == ["Delta Forum 2026"]
    text = held.read_text(encoding="utf-8")
    assert text.count("2026-c1  # RETIRED 2026-10-05 - duplicate of 2026-c2") == 1 and "2026-aes-x  # an older hold" in text
    assert RD.declared(held) == {"2026-aes-x", "2026-c1"}
    assert sqlite3.connect(db).execute("select count(*), group_concat(event_id) from grounding_facts").fetchone() == db_before     # nothing deleted, nothing changed
    assert list(mk.glob("Cybersecurity_audited.final.pre-retire-*.bak.csv"))
    assert _run(RD, args + ["--apply"], monkeypatch) == 0                                                  # idempotent: the row is gone, the line exists
    assert held.read_text(encoding="utf-8").count("RETIRED 2026-10-05") == 1


def test_a_customer_link_on_the_retired_row_is_reported_never_moved(tmp_path, monkeypatch, capsys):
    mk, data, db = _world(tmp_path)
    led = tmp_path / "l.txt"
    led.write_text("2026-10-05 | 2026-c1 | 2026-dupe-of-1 | upstream | https://x1.example/ | Alpha Con is held in the Grand Hall | the old name\n", encoding="utf-8")
    assert _run(RD, ["--ledger", str(led), "--markets-dir", str(mk), "--db", str(db), "--held-rows", str(tmp_path / "h.txt"), "--apply"], monkeypatch) == 0
    out = capsys.readouterr().out
    assert "a customer row (Submitted) is linked to the RETIRED row" in out
    assert sqlite3.connect(db).execute("select event_id, status from client_conferences").fetchall() == [("2026-dupe-of-1", "Submitted")]


def test_a_retired_pair_is_decided_for_the_duplicate_report_and_the_merge_tool():
    from scripts.find_duplicate_events import load_decisions
    dec = load_decisions()
    pair = frozenset(("2026-german-owasp-day-karlsruhe", "2026-owasp-german-chapter-conference-karlsruhe"))
    assert pair in dec and dec[pair][2].startswith("RETIRED")
