"""The Awards page shows researched-but-not-approved awards as PROVISIONAL (ACT-68) - and only those, and never as something they are not.

Pinned: no 'Deadline confirmed' verdict and no confidence badge on a provisional row, even when a checks file happens to carry its upstream id; an Open row is never past its deadline; the customer
sees one plain sentence and no internal words; the reader can hide the rows; a customer-listed row stays and a true non-award nobody lists stays out; conferences are not wired."""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("brp", ROOT / "scripts" / "build_review_page.py")
brp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brp)

SENTENCE = "Researched this week; our final checks are still running."


def row(**kw):
    base = {k: "" for k in brp.FIELDS}
    base.update({"EVENT_ID": "2027-thing-awards", "CONFERENCE": "Thing Awards", "Market": "Utility", "OPPORTUNITY_TYPE": "Awards", "STATUS": "Open"})
    base.update(kw)
    return base


def test_a_provisional_row_has_no_verdict_and_no_confidence_badge_even_if_a_check_exists_for_its_id():
    r = row(**{"_PROVISIONAL": "1", "GROUNDING_CONFIDENCE": "Verified (2027)", "SUBMISSION DEADLINE": "2027-02-01"})
    out = brp.build([r], "2026-10-12", checks={"2027-thing-awards": {"v": "verified", "u": "https://x/", "q": "quote"}})[0]
    assert out["prov"] is True and out["chk"] == "" and out["chku"] == "" and out["chkq"] == "" and out["c"] == ""


def test_an_ordinary_row_is_not_provisional():
    out = brp.build([row()], "2026-10-12")[0]
    assert out["prov"] is False


def test_the_status_of_a_provisional_row_is_derived_like_any_other():
    r = row(**{"_PROVISIONAL": "1", "SUBMISSION DEADLINE": "2026-10-09", "STATUS": "Open"})
    # the module hands the builder a status already derived; the builder's own derivation must agree and never leave Open past the date
    from scripts import provisional_rows as pr
    fixed = pr.derive_status(r, date(2026, 10, 12))
    assert brp.build([fixed], "2026-10-12")[0]["s"] == "Closed"


def test_the_template_derives_closed_for_an_open_row_past_its_deadline_and_handles_provisional():
    t = brp.PAGE
    assert "r.dd<0 && (r.s==='Open'||r.s==='Upcoming')" in t
    assert "r.prov?' <span class=\"b b-prov\"" in t and "Researched this week; our final checks are still running." in t
    assert 'id="showprov"' in t and "showProv" in t


def test_the_page_says_one_plain_sentence_and_no_internal_words():
    lines = [c for c in brp.PAGE.splitlines() if "prov" in c.lower()]
    assert lines, "the template has provisional markup"
    for chunk in lines:
        for word in ("tooling", "upstream", "canonical", "identity", "ACT-", "held", "gate", "id "):
            assert word not in chunk, (word, chunk)


def _write_world(tmp_path, approved_rows, raw_rows, identity):
    cols = list(dict.fromkeys(["EVENT_ID", *brp.FIELDS]))
    for name, rows in (("Awards_audited.final.csv", approved_rows), ("Awards_audited.csv", raw_rows)):
        with open(tmp_path / name, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    with open(tmp_path / "Awards_audited.identity.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["OUTPUT_EVENT_ID", "OUTPUT_CONFERENCE", "INPUT_CONFERENCE", "EVENT_ID_CANON"])
        for out_id, name, canon in identity:
            w.writerow([out_id, name, name, canon])


def test_provisional_awards_only_the_researched_unapproved_ones_after_the_awards_rule(tmp_path, monkeypatch):
    approved = [row(EVENT_ID="2027-have", CONFERENCE="Have Awards")]
    raw = [row(EVENT_ID="2027-have-r", CONFERENCE="Have Awards"), row(EVENT_ID="2027-new", CONFERENCE="New Awards", **{"SUBMISSION DEADLINE": "2026-12-01"}),
           row(EVENT_ID="2027-speak", CONFERENCE="A Speaking Event", OPPORTUNITY_TYPE="Speaking"), row(EVENT_ID="2027-listed", CONFERENCE="Listed Speaking Thing", OPPORTUNITY_TYPE="Speaking"),
           row(EVENT_ID="2027-noname", CONFERENCE="  ")]
    _write_world(tmp_path, approved, raw, [("2027-have-r", "Have Awards", "perm-have"), ("2027-new", "New Awards", ""), ("2027-speak", "A Speaking Event", ""),
                                           ("2027-listed", "Listed Speaking Thing", ""), ("2027-noname", "x", "")])
    from scripts import provisional_rows as pr
    monkeypatch.setattr(pr, "awards_lookup", lambda db: {"2027-have": "perm-have"})
    customer = {"names": {"listed speaking thing"}, "urls": set()}
    got = brp.provisional_awards(approved, tmp_path, "unused.db", "2026-10-12", customer)
    names = sorted(r["CONFERENCE"] for r in got)
    assert names == ["Listed Speaking Thing", "New Awards"], "a true non-award nobody lists stays out; a customer-listed one stays in; a nameless one is skipped; an approved one is not provisional"
    assert all(r["_PROVISIONAL"] == "1" for r in got)


def test_a_fault_reading_the_research_builds_the_page_without_provisional_rows(tmp_path, capsys):
    got = brp.provisional_awards([], tmp_path / "does-not-exist", None, "2026-10-12", None)
    assert got == [] and "no provisional rows" in capsys.readouterr().out


def test_conference_pages_refuse_the_provisional_flag(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in.csv"
    src.write_text(",".join(["EVENT_ID", "CONFERENCE", "Market"]) + "\nx,Y,Utility\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["build_review_page.py", "-i", str(src), "-o", str(tmp_path / "o.html"), "--kind", "conference", "--no-evidence", "--provisional-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as e:
        brp.main()
    assert "awards page only" in str(e.value)


def test_a_built_page_marks_the_row_and_offers_the_switch(tmp_path, monkeypatch):
    approved = [row(EVENT_ID="2027-have", CONFERENCE="Have Awards", **{"SUBMISSION DEADLINE": "2027-05-01"})]
    raw = [row(EVENT_ID="2027-new", CONFERENCE="New Awards", **{"SUBMISSION DEADLINE": "2026-12-01"})]
    _write_world(tmp_path, approved, raw, [("2027-new", "New Awards", "")])
    from scripts import provisional_rows as pr
    monkeypatch.setattr(pr, "awards_lookup", lambda db: {"2027-have": "perm-have"})
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    for c in ("arnica-awards", "utility-awards"):
        (snaps / f"{c}.csv").write_text("AWARD,SUBMISSION URL\nNew Awards,https://n.example/a/b\nHave Awards,https://h.example/a/b\n", encoding="utf-8")
    out = tmp_path / "Awards Review.html"
    monkeypatch.setattr(sys, "argv", ["build_review_page.py", "-i", str(tmp_path / "Awards_audited.final.csv"), "-o", str(out), "--kind", "awards", "--no-evidence", "--date", "2026-10-12",
                                      "--customer-awards-dir", str(snaps), "--provisional-dir", str(tmp_path), "--db", "unused.db"])
    brp.main()
    html = out.read_text(encoding="utf-8")
    data = json.JSONDecoder().raw_decode(html[html.index("const DATA = ") + len("const DATA = "):])[0]
    assert {d["n"]: d["prov"] for d in data} == {"Have Awards": False, "New Awards": True}
    assert "2 awards (1 provisional)" in html and "Show <i>Provisional</i> rows (1)" in html and "display:block" in html
    assert SENTENCE in html
    out2 = tmp_path / "No prov.html"
    monkeypatch.setattr(sys, "argv", ["build_review_page.py", "-i", str(tmp_path / "Awards_audited.final.csv"), "-o", str(out2), "--kind", "awards", "--no-evidence", "--date", "2026-10-12",
                                      "--customer-awards-dir", str(snaps)])
    brp.main()
    h2 = out2.read_text(encoding="utf-8")
    assert "(1 provisional)" not in h2 and 'id="provbox" style="display:none' in h2, "no provisional rows: the switch is hidden"
