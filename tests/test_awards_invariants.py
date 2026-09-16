"""Awards get reconciled too - and a deliberate exclusion is not data loss.

Contract v2.1 made awards a second entity type in their own table, and every invariant written
before 2026-09-15 looked only at conferences. That asymmetry let all 119 award rows sit at
`unverified` from the day the table existed until 2026-09-14, because the pass that would set
it did not exist and nothing was reconciling the table against anything.

These pin the awards checks, and especially the distinction the first run got wrong: eight
delivered rows were absent from the database ON PURPOSE, and a check that calls that data loss
teaches people to stop running the check.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor.storage import Store              # noqa: E402

SCRIPT = ROOT / "scripts" / "check_invariants.py"
DELIVERY_COLS = ["EVENT_ID", "CONFERENCE", "OPPORTUNITY_TYPE", "Market"]


def _build(tmp_path, awards, delivered, markets=True):
    """A database with awards rows, a seed so the run is allowed to report, and a delivery."""
    seeds = tmp_path / "market_sheets"
    seeds.mkdir(exist_ok=True)
    db = tmp_path / "t.db"
    Store(str(db)).db.close()
    con = sqlite3.connect(str(db))
    con.execute("alter table award_grounding_facts add column upstream_event_id TEXT")
    for a in awards:
        cols = ", ".join(a)
        con.execute(f"insert into award_grounding_facts ({cols})"
                    f" values ({', '.join('?' for _ in a)})", list(a.values()))
        if markets:
            con.execute("insert into award_markets (award_key, market) values (?,?)",
                        (a["event_id"], "Cybersecurity"))
    # one conference row + seed, so the conference half of the run has something to check
    con.execute("insert into grounding_facts (event_id, name, verify_state)"
                " values ('2027-x-houston','X 2027','verified')")
    # check 6 asks whether the weekly sweep has run at all; without a row every case here
    # would fail on a conference check rather than on the awards one under test
    con.execute("create table if not exists link_checks (url text)")
    con.execute("insert into link_checks (url) values ('https://x.test')")
    con.commit()
    con.close()
    with open(seeds / "x_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "EVENT_ID_CANON"])
        w.writeheader()
        w.writerow({"EVENT_ID": "x", "EVENT_ID_CANON": "2027-x-houston"})
    d = tmp_path / "Awards_out.csv"
    with open(d, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DELIVERY_COLS)
        w.writeheader()
        w.writerows(delivered)
    return db, d, seeds


def _run(db, delivery, seeds):
    p = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db),
                        "--awards-delivery", str(delivery), "--seed-dir", str(seeds)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _award(event_id, upstream, name="An Award", verify_state="verified",
           opens="", deadline=""):
    return {"event_id": event_id, "upstream_event_id": upstream, "name": name,
            "verify_state": verify_state, "submission_opens": opens, "deadline": deadline}


def _delivered(eid, name="An Award", opportunity="Awards"):
    return {"EVENT_ID": eid, "CONFERENCE": name, "OPPORTUNITY_TYPE": opportunity,
            "Market": "Cybersecurity"}


def test_a_delivered_award_that_vanished_is_a_failure(tmp_path):
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1")],
                          [_delivered("up-1"), _delivered("up-2", "Lost Award")])
    code, out = _run(db, d, seeds)
    assert code == 1
    assert "14 no delivered award is missing" in out
    assert re.search(r"\[FAIL\] 14", out)


def test_a_row_excluded_for_a_stated_reason_is_not_data_loss(tmp_path):
    """The first live run called eight deliberate exclusions data loss. The importer drops rows
    whose OPPORTUNITY_TYPE is not an award - the awards market file carries a few Speaking and
    Registration rows - and a check that cannot tell that apart from a lost row is noise."""
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1")],
                          [_delivered("up-1"),
                           _delivered("up-2", "A Talk", opportunity="Speaking"),
                           _delivered("up-3", "A Ticket", opportunity="Registration")])
    code, out = _run(db, d, seeds)
    assert code == 0, out
    assert "2 delivered award(s) absent BY DECISION" in out
    assert "not an award" in out


def test_a_table_nobody_ever_checked_is_reported(tmp_path):
    """The gap that started this: 119 rows at 'unverified' from the day the table was created,
    with nothing anywhere reporting a problem."""
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1", verify_state="unverified")],
                          [_delivered("up-1")])
    code, out = _run(db, d, seeds)
    assert code == 1
    assert "11 the awards evidence pass has run" in out
    assert "check_award_deadlines.py --apply" in out


def test_some_rows_unverified_is_normal_and_does_not_fail(tmp_path):
    """The inversion. 19 awards carry no cited page and 6 cite a page we could not open - those
    are honestly unverified, and failing on them would make the check unrunnable."""
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1", verify_state="verified"),
                                     _award("a2", "up-2", verify_state="unverified")],
                          [_delivered("up-1"), _delivered("up-2")])
    code, out = _run(db, d, seeds)
    assert code == 0, out
    assert "[ok  ] 11" in out


def test_a_window_that_closes_before_it_opens_is_a_failure(tmp_path):
    """The awards analogue of gate check 6b. An award has no event to attend, so 'deadline after
    the event starts' has no meaning - what it has instead is a window."""
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1", opens="2027-06-01",
                                            deadline="2027-03-01")],
                          [_delivered("up-1")])
    code, out = _run(db, d, seeds)
    assert code == 1
    assert "13 an award window opens before it closes" in out


def test_a_normal_window_passes(tmp_path):
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1", opens="2027-03-01",
                                            deadline="2027-06-01")],
                          [_delivered("up-1")])
    code, out = _run(db, d, seeds)
    assert code == 0, out


def test_an_award_on_no_market_list_is_reported(tmp_path):
    """115 of 401 conferences had drifted off every market list before anyone noticed. Awards
    are clean today; this is what keeps them so."""
    db, d, seeds = _build(tmp_path, [_award("a1", "up-1")], [_delivered("up-1")],
                          markets=False)
    code, out = _run(db, d, seeds)
    assert code == 1
    assert "12 every award is on a market list" in out


def test_the_awards_checks_are_skipped_when_there_are_no_awards(tmp_path):
    """A database with no awards table content must not fail the conference run."""
    db, d, seeds = _build(tmp_path, [], [])
    code, out = _run(db, d, seeds)
    assert code == 0, out
    assert "10 award event_id is unique" not in out
