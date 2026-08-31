"""N1 and N2: the two defects that had already fired.

N1  Nothing compared CITATIONS between the database and the delivery. Row presence was
    checked from the beginning; content never was. On 2026-08-29 amendment v1.4 cleared 184
    citations from the delivery and the database kept 179 of them, and the two stores
    disagreed silently for two days. Worse, refresh_delivery carries database values INTO the
    delivery, so the next routine refresh would have written them all back and undone v1.4.

N2  refresh_delivery broke R11 by construction. IS_PROJECTED is in its OWNED set;
    GROUNDING_CONFIDENCE has no database column at all. It wrote one half of a bound pair and
    could not write the other, guaranteeing an R11 failure whenever the projection flag moved.
    It moved on 4 rows on 2026-08-31 and only the acceptance gate caught it.

Both were found by luck - a dry run that happened to be read, and a gate run that happened to
happen. These tests are what replaces the luck.
"""
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_ci", ROOT / "scripts" / "check_invariants.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)

from src.cfp_monitor import rules          # noqa: E402

COLS = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL",
        "DEADLINE_QUOTE", "IS_PROJECTED", "GROUNDING_CONFIDENCE"]


def _delivery(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return path


def _row(eid="e1", name="Conf", deadline="", url="", quote=""):
    return {"EVENT_ID": eid, "CONFERENCE": name, "SUBMISSION DEADLINE": deadline,
            "DEADLINE_EVIDENCE_URL": url, "DEADLINE_QUOTE": quote,
            "IS_PROJECTED": "false", "GROUNDING_CONFIDENCE": "Verified (2026)"}


def _db(path, rows):
    con = sqlite3.connect(path)
    con.execute("create table grounding_facts (event_id text, deadline text, "
                "deadline_evidence_url text, deadline_quote text)")
    con.executemany("insert into grounding_facts values (?,?,?,?)", rows)
    con.commit()
    con.close()
    return str(path)


# ------------------------------------------------------------------ N1

def test_it_catches_a_citation_the_database_kept_after_the_delivery_cleared_it(tmp_path,
                                                                               monkeypatch):
    """THE AUGUST FAILURE, exactly. The delivery was cleared; the database was not."""
    db = _db(tmp_path / "t.db", [("e1", "", "https://example.org/cfp", "Deadline 1 May")])
    d = _delivery(tmp_path / "d.csv", [_row("e1", "Cleared Conf")])
    monkeypatch.setattr(ci, "_seed_map_cached", None, raising=False)
    import scripts.apply_resolutions as ar
    monkeypatch.setattr(ar, "_seed_map", lambda s: ({"e1": "e1"}, []))
    out = ci.citation_drift(db, Path(d))
    assert len(out) == 1
    assert "Cleared Conf" in out[0]
    assert "delivery blank, database holds one" in out[0]


def test_it_catches_the_reverse_too(tmp_path, monkeypatch):
    db = _db(tmp_path / "t.db", [("e1", "2026-05-01", "", "")])
    d = _delivery(tmp_path / "d.csv",
                  [_row("e1", "Kept Conf", "2026-05-01", "https://example.org/cfp", "q")])
    import scripts.apply_resolutions as ar
    monkeypatch.setattr(ar, "_seed_map", lambda s: ({"e1": "e1"}, []))
    out = ci.citation_drift(db, Path(d))
    assert len(out) == 1 and "database blank, delivery holds one" in out[0]


def test_it_catches_two_stores_citing_different_pages(tmp_path, monkeypatch):
    db = _db(tmp_path / "t.db", [("e1", "2026-05-01", "https://a.example/cfp", "q")])
    d = _delivery(tmp_path / "d.csv",
                  [_row("e1", "Split Conf", "2026-05-01", "https://b.example/cfp", "q")])
    import scripts.apply_resolutions as ar
    monkeypatch.setattr(ar, "_seed_map", lambda s: ({"e1": "e1"}, []))
    out = ci.citation_drift(db, Path(d))
    assert len(out) == 1 and "DIFFERENT pages" in out[0]


def test_agreement_is_silent(tmp_path, monkeypatch):
    """GOOD INPUT MUST SURVIVE. A check that fires on agreement is noise."""
    db = _db(tmp_path / "t.db", [("e1", "2026-05-01", "https://a.example/cfp", "q")])
    d = _delivery(tmp_path / "d.csv",
                  [_row("e1", "Agreeing", "2026-05-01", "https://a.example/cfp", "q")])
    import scripts.apply_resolutions as ar
    monkeypatch.setattr(ar, "_seed_map", lambda s: ({"e1": "e1"}, []))
    assert ci.citation_drift(db, Path(d)) == []


def test_no_id_map_reports_that_it_did_not_run(tmp_path, monkeypatch):
    """Silence must never be mistaken for agreement. Without the map every row fails to join,
    and 'no drift' would be a confident answer to a question never asked."""
    db = _db(tmp_path / "t.db", [("e1", "", "https://a.example/cfp", "q")])
    d = _delivery(tmp_path / "d.csv", [_row("e1")])
    import scripts.apply_resolutions as ar
    monkeypatch.setattr(ar, "_seed_map", lambda s: ({}, []))
    out = ci.citation_drift(db, Path(d))
    assert len(out) == 1 and "did NOT run" in out[0]


def test_the_check_is_a_watch_not_a_failure():
    """A drift means the two stores disagree and a PERSON must decide which is right. Failing
    the run would block the gate everywhere while that waits, and the usual response to that
    is to stop running the check."""
    src = (ROOT / "scripts" / "check_invariants.py").read_text(encoding="utf-8")
    assert 'res.add("9  citations agree with the delivery"' in src
    assert "fatal=False" in src.split('res.add("9')[1][:400]


def test_skipping_the_check_says_so_out_loud():
    """Without --delivery the check cannot run. Printing nothing would let a run that never
    compared the stores look identical to one that compared them and found nothing."""
    src = (ROOT / "scripts" / "check_invariants.py").read_text(encoding="utf-8")
    assert "[skip ] 9" in src
    assert "pass --delivery to run this" in src


# ------------------------------------------------------------------ N2

def test_refresh_binds_confidence_whenever_it_writes_the_projection_flag():
    """rules.bound_confidence says in its own docstring: 'Call this WHENEVER IS_PROJECTED
    changes. Not calling it is the single most repeated defect in this codebase.' This script
    was not calling it."""
    src = (ROOT / "scripts" / "refresh_delivery.py").read_text(encoding="utf-8")
    assert "rules.bound_confidence" in src
    assert 'col == "IS_PROJECTED"' in src
    assert "from src.cfp_monitor import rules" in src


def test_the_binding_rule_itself_still_holds_both_directions():
    assert rules.bound_confidence("Verified (2027)", True) == "Projected (2027)"
    assert rules.bound_confidence("Projected (2027)", False) == "Verified (2027)"


def test_a_blank_confidence_is_left_blank():
    """An honest blank is not a value to 'correct' (2.6)."""
    assert rules.bound_confidence("", True) == ""
    assert rules.bound_confidence("   ", False).strip() == ""
