"""Check 3 must not read an anti-bot notice as "the quote is not on the page" (Global Energy Show, 2026-10-01/02).

Incapsula answers 200 with an 84-character notice. The gate's check 3 treated it as the page and reported
"quote and date both absent", so a correct approved row was REJECTED every week. A walled page is now exempt like
a 403 - and REPORTED, so an unread page never looks like a checked one. A live call with a real page that lacks
its quote must still fail.
"""
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

INCAPSULA = "Request unsuccessful. Incapsula incident ID: 260000060773792091-441289197983367596"
URL = "https://example.org/call"
QUOTE = "all submissions must be completed through the online submission form by the December 4, 2026 deadline"


def _gate(page_text: str):
    cols = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE",
            "IS_PROJECTED", "STATUS", "SUBMISSION URL", "CFP_SUBMISSION_URL"]
    row = {c: "" for c in cols}
    row.update({"EVENT_ID": "x-2027-speaking", "CONFERENCE": "Test Energy Show 2027", "SUBMISSION DEADLINE": "2026-12-04",
                "DEADLINE_EVIDENCE_URL": URL, "DEADLINE_QUOTE": QUOTE, "IS_PROJECTED": "false"})
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow(row)
    g = ad.Gate(fh.name, network=True)
    g.today = date(2026, 10, 2)
    with open(fh.name, encoding="utf-8-sig", newline="") as f:
        g.rows = list(csv.DictReader(f))
    real_ft, real_ls = ad.fetch_text, ad.link_status
    ad.fetch_text = lambda url, *a, **k: (page_text, "")
    ad.link_status = lambda url, *a, **k: (200, "ok")
    try:
        g.check_citations()
    finally:
        ad.fetch_text, ad.link_status = real_ft, real_ls
    return g


def _check3(g):
    return next(r for r in g.results if r[0] == "3")


def test_a_walled_page_is_not_a_failed_quote_and_is_reported():
    g = _gate(INCAPSULA)
    num, name, ok, failures = _check3(g)
    assert ok, f"walled page rejected the row: {failures}"
    assert any(n[0] == "3" and URL in " ".join(n[2]) for n in g.notes), "walled page passed silently"


def test_a_real_page_without_the_quote_still_fails():
    g = _gate("Call for submissions. " + "The programme committee meets in spring. " * 40)
    num, name, ok, failures = _check3(g)
    assert not ok and "quote and date both absent" in failures[0]


def test_a_real_page_with_the_quote_passes_with_no_note():
    g = _gate("Intro text. " + QUOTE + ". More text. " * 30)
    num, name, ok, failures = _check3(g)
    assert ok and not [n for n in g.notes if n[0] == "3"]


# ---- script-built pages (a plain fetch sees almost no text), operator-approved 2026-10-02 --------------------------------
SHELL = "BASC 2027 · Boston Application Security Conference"


def test_a_script_built_page_is_not_a_failed_quote_and_is_reported():
    g = _gate(SHELL)
    num, name, ok, failures = _check3(g)
    assert ok, f"script-built page rejected the row: {failures}"
    notes = [n for n in g.notes if n[0] == "3"]
    assert notes and "script-built page" in " ".join(notes[0][2])
    assert any(URL in " ".join(n[2]) for n in notes), "script-built page passed silently"


def test_a_short_page_that_carries_the_quote_still_passes_with_no_note():
    g = _gate(QUOTE)                                   # short, but the quote is on it
    assert _check3(g)[2] and not [n for n in g.notes if n[0] == "3"]


def test_an_empty_fetch_is_not_treated_as_a_script_shell():
    from src.cfp_monitor.verify import is_script_shell
    assert not is_script_shell("") and not is_script_shell(None) and is_script_shell("x" * 199) and not is_script_shell("x" * 200)


def test_a_normal_sized_page_without_the_quote_still_fails_after_the_change():
    g = _gate("Call for submissions. " + "The programme committee meets in spring. " * 40)
    assert not _check3(g)[2]


def test_substance_note_when_rows_claim_nothing():
    """An empty claim passes every check; the gate must say so (advisory, never a failure)."""
    cols = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_QUOTE"]
    g = ad.Gate.__new__(ad.Gate)
    g.notes, g.results = [], []
    g.rows = [{"EVENT_ID": f"e{i}", "CONFERENCE": f"Conf {i}", "SUBMISSION DEADLINE": "", "DEADLINE_QUOTE": ""} for i in range(6)]
    ad.Gate.check_substance(g)
    assert g.notes and g.notes[0][0] == "S" and g.results == []                # a note, not a result: it cannot fail the gate
    g.notes = []
    g.rows[0].update({"SUBMISSION DEADLINE": "2026-12-04", "DEADLINE_QUOTE": "q"})
    ad.Gate.check_substance(g)
    assert not g.notes, "a small file notes only when EVERY row is empty (one researched row means research happened)"
    g.notes = []
    g.rows = [{"EVENT_ID": f"e{i}", "CONFERENCE": f"Conf {i}", "SUBMISSION DEADLINE": "" if i < 6 else "2026-12-04", "DEADLINE_QUOTE": "" if i < 6 else "q"} for i in range(10)]
    ad.Gate.check_substance(g)
    assert g.notes, "a file of 10 or more notes when half the rows are empty"
    g.notes = []
    g.rows = [{"EVENT_ID": f"e{i}", "CONFERENCE": f"Conf {i}", "SUBMISSION DEADLINE": "2026-12-04", "DEADLINE_QUOTE": "q"} for i in range(6)]
    ad.Gate.check_substance(g)
    assert not g.notes
