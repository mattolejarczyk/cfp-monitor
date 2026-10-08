"""ACT-51 phase 2: scripts/customer_auto_add.py adds the customer rows that are NOT in the research queue, by a gate, with a dry-run default. FIXTURES ONLY (tmp_path); nothing live is read or written."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from scripts import customer_auto_add as ca          # noqa: E402
from scripts import customer_coverage as cc          # noqa: E402
from test_customer_coverage import make_world, TODAY  # noqa: E402


def go(tmp_path, client_rows, cyb_inputs, apply=False, cap=10, **kw):
    db, md, led = make_world(tmp_path, client_rows, cyb_inputs, **kw)
    out = tmp_path / "out"
    lines, code = ca.run(TODAY, db, md, led, out, cap, apply)
    return lines, md, out


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


NEW = {"name": "Brand New Summit 2027", "url": "https://newsummit.example/2027", "start": "2027-03-10", "loc": "Berlin, Germany"}
HELD_OTHER_YEAR = {"CONFERENCE": "Old Con 2026", "CONFERENCE URL": "https://oldcon.example/2026", "START DATE": "3/3/2026", "EVENT_ID_CANON": "x-1"}


def test_dry_run_proposes_but_writes_nothing_to_the_input_list(tmp_path):
    lines, md, out = go(tmp_path, [NEW], [])
    assert lines[0].startswith("AUTOADD: mode=dry-run; 1 to add, 0 held for a person") and "1 customer rows NOT in the queue" in lines[0]
    assert read(md / "Cybersecurity_input.csv") == []
    prop = read(out / "proposed_additions.csv")
    assert [p["conference"] for p in prop] == ["Brand New Summit 2027"]
    assert "Brand New Summit 2027" in (out / "request_to_upstream_2026-10-06.md").read_text(encoding="utf-8")
    assert "nothing is sent by code" in (out / "request_to_upstream_2026-10-06.md").read_text(encoding="utf-8")


def test_apply_appends_a_blank_id_row_proves_old_rows_unchanged_and_the_row_is_then_in_the_queue(tmp_path):
    keep = {"CONFERENCE": "Kept Con 2027", "CONFERENCE URL": "https://kept.example/2027", "START DATE": "5/5/2027", "EVENT_ID_CANON": "kept-2027"}
    lines, md, out = go(tmp_path, [NEW], [keep], apply=True)
    assert lines[0].startswith("AUTOADD: mode=applied; 1 added") and "0 customer rows NOT in the queue" in lines[0]
    rows = read(md / "Cybersecurity_input.csv")
    assert [r["CONFERENCE"] for r in rows] == ["Kept Con 2027", "Brand New Summit 2027"]
    assert rows[0]["EVENT_ID_CANON"] == "kept-2027" and rows[1]["EVENT_ID_CANON"] == "", "an id is never minted"
    assert rows[1]["Market"] == "Cybersecurity" and rows[1]["START DATE"] == "3/10/2027" and rows[1]["RESEARCH STATUS"] == "Needs Verification"
    assert list(md.glob("Cybersecurity_input.pre-customerrows-*.bak.csv")), "the existing writer's backup"
    assert not any("NOT PICKED UP" in l for l in lines)
    assert "Brand New Summit 2027" in (out / "request_to_upstream_2026-10-06.md").read_text(encoding="utf-8")   # a blank-id row waits for an id


def test_second_apply_adds_nothing(tmp_path):
    db, md, led = make_world(tmp_path, [NEW], [])
    out = tmp_path / "out"
    ca.run(TODAY, db, md, led, out, 10, True)
    lines, _ = ca.run(TODAY, db, md, led, out, 10, True)
    assert lines[0].startswith("AUTOADD: mode=applied; 0 added") and len(read(md / "Cybersecurity_input.csv")) == 1


def test_linked_but_missing_row_is_held_not_added(tmp_path):
    lines, md, out = go(tmp_path, [{**NEW, "event_id": "UP-1"}], [])
    assert "0 to add, 1 held" in lines[0] and lines[1].startswith("AUTOADD HELD: Brand New Summit 2027")
    assert "linked to an event we hold" in (out / "auto_add.md").read_text(encoding="utf-8")
    assert read(out / "proposed_additions.csv") == []


def test_edition_guard_holds_a_row_on_a_website_the_list_already_has(tmp_path):
    cust = {"name": "Old Con 2027", "url": "https://www.oldcon.example/2027", "start": "2027-03-03"}
    lines, md, out = go(tmp_path, [cust], [HELD_OTHER_YEAR], apply=True)
    assert "0 added, 1 held" in lines[0]
    assert "edition guard" in (out / "auto_add.md").read_text(encoding="utf-8")
    assert len(read(md / "Cybersecurity_input.csv")) == 1, "nothing written"
    assert any(l.startswith("AUTOADD NOT PICKED UP: Old Con 2027") for l in lines), "added-but-not-picked-up is named loudly"


def test_row_without_a_url_is_held(tmp_path):
    lines, md, out = go(tmp_path, [{"name": "No Link Expo", "url": "", "start": "2027-06-06"}], [])
    assert "0 to add, 1 held" in lines[0]
    assert "no URL" in (out / "auto_add.md").read_text(encoding="utf-8")


def test_cap_adds_nothing_for_a_market_over_the_cap(tmp_path):
    many = [{"name": f"Fresh Event {i}", "url": f"https://fresh{i}.example/2027", "start": "2027-04-01"} for i in range(4)]
    lines, md, out = go(tmp_path, many, [], apply=True, cap=3)
    assert "0 added, 4 held" in lines[0] and read(md / "Cybersecurity_input.csv") == []
    assert "cap: 4 rows" in (out / "auto_add.md").read_text(encoding="utf-8")
    lines, md, out = go(tmp_path / "ok", many[:3], [], apply=True, cap=3)
    assert "3 added" in lines[0]


def test_event_already_started_is_not_added(tmp_path):
    lines, md, out = go(tmp_path, [{"name": "Past Summit", "url": "https://past.example/", "start": "2026-10-06"}], [], apply=True)
    # coverage counts a start of today as ahead; add_customer_rows skips what starts before today only, so it is added; a date before today is excluded by coverage itself
    assert lines[0].startswith("AUTOADD: mode=applied")
    lines, md, out = go(tmp_path / "b", [{"name": "Gone Summit", "url": "https://gone.example/", "start": "2026-09-01"}], [])
    assert "0 to add, 0 held" in lines[0]


def test_unreadable_database_reports_unknown_and_never_raises(tmp_path):
    lines, _ = ca.run(TODAY, tmp_path / "missing.db", tmp_path, tmp_path / "l.csv", tmp_path / "out", 10, False)
    assert lines[0].startswith("AUTOADD: UNKNOWN")


def test_apply_on_the_live_markets_folder_is_refused_without_live(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["customer_auto_add.py", "--apply", "--markets-dir", str(cc.MARKETS), "--db", str(ROOT / "nope.db")])
    assert ca.main() == 0
    assert "REFUSED" in capsys.readouterr().out


def test_registered_domain():
    assert ca.registered_domain("https://www.conf.example.co.uk/2027") == "example.co.uk"
    assert ca.registered_domain("newyork.theaisummit.com/x") == "theaisummit.com"
    assert ca.registered_domain("") == ""
