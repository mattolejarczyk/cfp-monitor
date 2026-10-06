"""scripts/add_customer_rows.py: customer-tracked events go onto the research input list (ACT-51)."""
import csv
from pathlib import Path

import pytest

from scripts import add_customer_rows as acr

COLS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "CONFERENCE DATES", "STATUS", "RESEARCH STATUS", "EDITION", "START DATE", "Market", "EVENT_ID_CANON"]


def _write(path: Path, rows, bom=True, crlf=True):
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows(rows)


def _cls(**kw):
    base = {"class": "C", "sheet": "arnica", "conference": "New Summit", "customer_url": "https://old.example/", "customer_location": "Paris, France", "customer_start": "11/03/2026",
            "page_confirmed": "yes", "page_start_date": "2026-11-02", "evidence_url": "https://new.example/"}
    base.update(kw)
    return base


def test_new_row_uses_page_date_url_and_leaves_the_id_blank():
    r = acr.new_row(_cls(), COLS, "Cybersecurity")
    assert r["CONFERENCE"] == "New Summit" and r["CONFERENCE URL"] == "https://new.example/"
    assert r["START DATE"] == "11/2/2026" and r["EDITION"] == "2026"      # page date, the lists' M/D/YYYY format
    assert r["EVENT_ID_CANON"] == "" and r["Market"] == "Cybersecurity" and r["RESEARCH STATUS"] == "Needs Verification"


def test_unconfirmed_row_falls_back_to_the_customers_own_date_and_url():
    r = acr.new_row(_cls(page_confirmed="no", page_start_date="2026-12-31", evidence_url="https://wrong/"), COLS, "Cybersecurity")
    assert r["CONFERENCE URL"] == "https://old.example/" and r["START DATE"] == "11/3/2026"


def test_plan_skips_other_classes_held_names_and_events_that_start_too_soon():
    inputs = {"Cybersecurity": [{"CONFERENCE": "Already Here", **{c: "" for c in COLS if c != "CONFERENCE"}}], "Utility": []}
    cols = {"Cybersecurity": COLS, "Utility": COLS}
    rows = [_cls(conference="Fresh One"), _cls(conference="already here"), _cls(conference="Too Soon", page_start_date="2026-10-07"),
            _cls(conference="Held Elsewhere", **{"class": "A"}), _cls(conference="Undated", page_confirmed="no", page_start_date="", customer_start=""), _cls(conference="Util Event", sheet="utility"), _cls(conference="Fresh One")]
    add, skipped = acr.plan(rows, inputs, cols, "2026-10-11")
    assert [r["CONFERENCE"] for r in add["Cybersecurity"]] == ["Fresh One", "Undated"]   # the duplicate of Fresh One is skipped; an undated event is still researched
    assert [r["CONFERENCE"] for r in add["Utility"]] == ["Util Event"] and add["Utility"][0]["Market"] == "Utility"
    why = dict(skipped)
    assert "already on the input list" in why["already here"] and "before 2026-10-11" in why["Too Soon"]


def test_write_appends_only_and_proves_the_old_rows_unchanged(tmp_path):
    p = tmp_path / "Cybersecurity_input.csv"
    old = [{**{c: "" for c in COLS}, "CONFERENCE": "Old One", "EVENT_ID_CANON": "2026-old-one-x"}]
    _write(p, old)
    cols, rows, bom, crlf = acr.read_input(p)
    new = [acr.new_row(_cls(), cols, "Cybersecurity")]
    bak = acr.write_with_proof(p, cols, rows, new, bom, crlf)
    assert bak.exists() and bak.name.startswith("Cybersecurity_input.pre-customerrows-")
    _, after, bom2, crlf2 = acr.read_input(p)
    assert after[:1] == old and [r["CONFERENCE"] for r in after] == ["Old One", "New Summit"] and (bom2, crlf2) == (True, True)
    assert open(bak, encoding="utf-8-sig").read().count("New Summit") == 0         # the backup is the file as it was


def test_write_refuses_and_leaves_the_original_when_the_read_back_differs(tmp_path, monkeypatch):
    p = tmp_path / "Utility_input.csv"
    _write(p, [{**{c: "" for c in COLS}, "CONFERENCE": "Old One"}])
    before = p.read_bytes()
    cols, rows, bom, crlf = acr.read_input(p)
    monkeypatch.setattr(acr.csv.DictWriter, "writerows", lambda self, rs: None)    # a writer that drops the rows
    with pytest.raises(AssertionError):
        acr.write_with_proof(p, cols, rows, [acr.new_row(_cls(), cols, "Utility")], bom, crlf)
    assert p.read_bytes() == before and not (tmp_path / "Utility_input.csv.tmp").exists()
