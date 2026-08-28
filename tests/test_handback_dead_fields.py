"""The hand-back must cover every customer-facing field, and count what it prints.

Two defects found on 2026-08-27 while building the dead-link hand-back:

  1. It matched link_checks against `submission_url` ONLY, so an 80-link backlog produced a
     45-link document. The 35 it dropped were rows whose DEADLINE_EVIDENCE_URL or MAIN_INFO_URL
     is dead while the submit link still works. weekly_verify was widened to all four fields on
     2026-08-12 for exactly this reason; this matcher was never updated, and its comment still
     claimed "weekly_verify checks EVERY submission link". Same shape as clean_city: logic that
     was correct when written, whose premise expired without anything re-checking it.

  2. The summary counted (row, field) pairs while the table printed (row, url) lines, so the
     document announced "113" above a 76-row table. Both now derive from one list.
"""
import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_mh", ROOT / "scripts" / "make_handback.py")
mh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mh)

FIELDS = ("submission_url", "deadline_evidence_url", "main_info_url", "url")
COLS = ("event_id", "name", "verify_state", "verify_detail", "deadline", "deadline_quote",
        "conference_key", *FIELDS)


def _setup(tmp_path, rows, dead_urls, last_alive=None):
    db = tmp_path / "h.db"
    con = sqlite3.connect(db)
    con.execute(f"create table grounding_facts ({', '.join(f'{c} text' for c in COLS)})")
    for r in rows:
        vals = {c: "" for c in COLS}
        vals.update(r)
        con.execute(f"insert into grounding_facts values ({','.join('?' * len(COLS))})",
                    [vals[c] for c in COLS])
    con.execute("""create table link_checks (url text primary key, state text, checked_at text,
                   http_status integer, first_seen text, last_alive text)""")
    for u in dead_urls:
        con.execute("insert into link_checks values (?,?,?,?,?,?)",
                    (u, "dead", "2026-08-27T10:00:00", 404, "2026-07-01T00:00:00",
                     (last_alive or {}).get(u)))
    con.execute("""create table evidence (id integer, event_id text, field text,
                   value_claimed text, source_url text, quote text, origin text, method text,
                   fetched_at text, verdict text, found_quote text, detail text,
                   call_type text, exportable text, export_block text)""")
    con.commit()
    con.close()

    seeds = tmp_path / "seeds"
    seeds.mkdir()
    with open(seeds / "Test_seed.csv", "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=["EVENT_ID_CANON", "Market"])
        wtr.writeheader()
        for r in rows:
            wtr.writerow({"EVENT_ID_CANON": r["event_id"], "Market": "TestMarket"})

    out = tmp_path / "hb.md"
    return str(db), str(seeds), out


def _run(db, seeds, out, monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["make_handback.py", "--db", db, "--seed-dir", seeds, "--out", str(out)])
    mh.main()
    return out.read_text(encoding="utf-8")


DEADEV = "https://gone.example.com/evidence"
DEADSUB = "https://gone.example.com/submit"


def test_a_dead_deadline_evidence_url_reaches_the_handback(tmp_path, monkeypatch):
    """The 35 rows the old matcher dropped were exactly this shape."""
    txt = _run(*_setup(tmp_path, [{"event_id": "e1", "name": "Evidence Only Conf",
                                   "deadline_evidence_url": DEADEV,
                                   "submission_url": "https://fine.example.com/ok"}],
                       [DEADEV]), monkeypatch)
    assert DEADEV in txt, "a dead DEADLINE_EVIDENCE_URL must appear"
    assert "DEADLINE_EVIDENCE_URL" in txt, "and must be named, since the fix differs by field"


def test_a_dead_main_info_url_reaches_the_handback(tmp_path, monkeypatch):
    dead = "https://gone.example.com/home"
    txt = _run(*_setup(tmp_path, [{"event_id": "e1", "name": "Info Only Conf",
                                   "main_info_url": dead}], [dead]), monkeypatch)
    assert dead in txt


def test_one_url_in_four_fields_is_one_line_naming_all_four(tmp_path, monkeypatch):
    """Not four lines. This is the defect that made the weekly digest 119 lines for 80 URLs."""
    row = {"event_id": "e1", "name": "Four Fields Conf"}
    row.update(dict.fromkeys(FIELDS, DEADSUB))
    txt = _run(*_setup(tmp_path, [row], [DEADSUB]), monkeypatch)
    body = [ln for ln in txt.splitlines() if DEADSUB in ln and ln.startswith("|")]
    assert len(body) == 1, f"expected one table line, got {len(body)}"
    for label in ("SUBMISSION URL", "DEADLINE_EVIDENCE_URL", "MAIN_INFO_URL", "CONFERENCE URL"):
        assert label in body[0], f"{label} should be listed on the single line"


def test_two_distinct_dead_urls_on_one_row_are_two_lines(tmp_path, monkeypatch):
    """GOOD INPUT SURVIVES: deduping must not collapse genuinely different broken links."""
    txt = _run(*_setup(tmp_path, [{"event_id": "e1", "name": "Two Broken Conf",
                                   "submission_url": DEADSUB,
                                   "deadline_evidence_url": DEADEV}],
                       [DEADSUB, DEADEV]), monkeypatch)
    lines = [ln for ln in txt.splitlines() if ln.startswith("| Two Broken Conf")]
    assert len(lines) == 2


def test_a_live_link_is_not_reported(tmp_path, monkeypatch):
    """The other half of 'good input survives' - a working link must never appear."""
    live = "https://fine.example.com/ok"
    txt = _run(*_setup(tmp_path, [{"event_id": "e1", "name": "Healthy Conf",
                                   "submission_url": live}], []), monkeypatch)
    assert live not in txt


def test_the_never_count_matches_the_table(tmp_path, monkeypatch):
    """The summary said 113 above a 76-row table because it counted a different thing."""
    rows, dead = [], []
    for i in range(3):
        u = f"https://gone.example.com/{i}"
        rows.append({"event_id": f"e{i}", "name": f"Conf {i}", "submission_url": u,
                     "deadline_evidence_url": u})       # same URL twice on purpose
        dead.append(u)
    alive_once = {dead[0]: "2026-08-10T00:00:00"}
    txt = _run(*_setup(tmp_path, rows, dead, last_alive=alive_once), monkeypatch)

    table_never = sum(1 for ln in txt.splitlines()
                      if ln.startswith("|") and ln.rstrip().endswith("**never** |"))
    claimed = [ln for ln in txt.splitlines() if "NEVER seen the address resolve" in ln]
    assert claimed, "the summary line should be present"
    assert f"**{table_never}**" in claimed[0], (
        f"summary says {claimed[0]!r} but the table has {table_never} 'never' rows")
    assert table_never == 2, "two of the three URLs were never alive"
