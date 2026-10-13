"""'Awaiting research' rows (ACT-70 follow-up): every award on the customer's sheets that no row of the page carries is shown, built from the customer's own sheet only, clearly marked, with nothing
internal and no verdict; the page header and the second checkbox count them; the release gate counts them as ON the page."""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts import awaiting_rows as aw                                     # noqa: E402

ON = date(2026, 10, 13)
SENTENCE = "On your sheet. Research for this award is scheduled this week; results will appear in next week's page."


def sheet(name, url="", deadline="", location="", event="", client="arnica-awards", n=2):
    return {"client": client, "sheet_row": n, "name": name, "url": url, "location": location, "priority": "", "status": "", "deadline": deadline, "event_date": event}


def page(name, market="Cybersecurity", url=""):
    return {"CONFERENCE": name, "Market": market, "SUBMISSION URL": url}


def test_a_deadline_is_kept_only_when_the_cell_is_exactly_one_date():
    f = aw.single_iso_date
    assert f("11/05/2026") == "2026-11-05" and f("2026-11-05") == "2026-11-05" and f(" 1/2/2027 ") == "2027-01-02"
    for bad in ("", "Rolling", "Anticipated March 2027", "Early Bird: 03/13/2026; Regular: 05/01/2026", "11/05/2026 - 12/01/2026", "Entries open: 02/01/2027;", "13/45/2026"):
        assert f(bad) == "", bad


def test_only_awards_on_no_page_row_are_added_and_by_name_or_deep_url_never_an_id():
    pg = [page("Alpha Awards 2026"), page("Beta Prize", url="https://beta.example/awards/p"), page("Other Market Award", market="Utility")]
    sheets = {"arnica-awards": [sheet("Alpha Awards", n=2), sheet("Beta Programme", url="https://www.beta.example/awards/p/", n=3), sheet("Gamma Awards", url="https://g.example/a/b", n=4),
                                sheet("Other Market Award", n=5), sheet("Gamma Awards", n=6)]}
    rows, rep = aw.awaiting_candidates(pg, sheets, ON)
    assert [r["CONFERENCE"] for r in rows] == ["Gamma Awards", "Other Market Award"], "name key ignores years; a deep URL matches; a page row of the OTHER market does not count; a repeated name once"
    assert all(r["Market"] == "Cybersecurity" and r["_AWAITING"] == "1" and r["OPPORTUNITY_TYPE"] == "Awards" for r in rows)


def test_the_row_is_built_from_the_customers_sheet_only():
    sheets = {"utility-awards": [sheet("Future Award", url="https://f.example/x/y", deadline="12/01/2026", location="Oslo, Norway", event="03/10/2027", client="utility-awards"),
                                 sheet("Past Award", deadline="01/02/2026", client="utility-awards", n=3),
                                 sheet("Vague Award", deadline="Early Bird: 03/13/2026; Regular: 05/01/2026", client="utility-awards", n=4)]}
    rows, rep = aw.awaiting_candidates([], sheets, ON)
    f, p, v = rows
    assert f["Market"] == "Utility" and f["SUBMISSION DEADLINE"] == "2026-12-01" and f["STATUS"] == "Needs Verification" and f["SUBMISSION URL"] == "https://f.example/x/y" and f["CITY"] == "Oslo, Norway" and f["START DATE"] == "2027-03-10"
    assert p["STATUS"] == "Closed" and p["SUBMISSION DEADLINE"] == "2026-01-02", "a past award is shown Closed, not dropped"
    assert v["SUBMISSION DEADLINE"] == "" and v["STATUS"] == "Needs Verification" and v["STATUS DETAILS"] == "On your sheet: Early Bird: 03/13/2026; Regular: 05/01/2026"
    for r in rows:
        for k in ("GROUNDING_CONFIDENCE", "DEADLINE_QUOTE", "DEADLINE_EVIDENCE_URL", "CFP_SUBMISSION_URL"):
            assert not r.get(k)


def _brp():
    spec = importlib.util.spec_from_file_location("brp_aw", ROOT / "scripts" / "build_review_page.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _build(tmp_path, monkeypatch, flag=True):
    brp = _brp()
    src = tmp_path / "in.csv"
    src.write_text("EVENT_ID,CONFERENCE,Market,OPPORTUNITY_TYPE,STATUS,SUBMISSION DEADLINE,SUBMISSION URL\na,Have Awards,Cybersecurity,Awards,Open,2027-05-01,https://h.example/a/b\n", encoding="utf-8")
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    head = "AWARD,LOCATION,EVENT DATE,SUBMISSION DEADLINE,STATUS,PRIORITY,SUBMISSION URL\n"
    (snaps / "arnica-awards.csv").write_text(head + "Have Awards,,,,,,https://h.example/a/b\nNew Awards,Paris,,11/20/2026,,,https://n.example/a/b\nWord Awards,,,Anticipated March 2027,,,\n", encoding="utf-8")
    (snaps / "utility-awards.csv").write_text(head + "Old Utility Award,,,01/01/2026,,,https://u.example/a/b\n", encoding="utf-8")
    out = tmp_path / "Awards.html"
    argv = ["build_review_page.py", "-i", str(src), "-o", str(out), "--kind", "awards", "--no-evidence", "--date", "2026-10-13", "--customer-awards-dir", str(snaps)] + (["--awaiting-research"] if flag else [])
    monkeypatch.setattr(sys, "argv", argv)
    brp.main()
    html = out.read_text(encoding="utf-8")
    data = json.JSONDecoder().raw_decode(html[html.index("const DATA = ") + len("const DATA = "):])[0]
    return html, data, brp


def test_the_page_shows_the_rows_counts_them_and_offers_the_second_checkbox(tmp_path, monkeypatch):
    html, data, _ = _build(tmp_path, monkeypatch)
    by = {d["n"]: d for d in data}
    assert sorted(n for n, d in by.items() if d["aw"]) == ["New Awards", "Old Utility Award", "Word Awards"] and by["Have Awards"]["aw"] is False
    assert (by["New Awards"]["s"], by["New Awards"]["dl"], by["New Awards"]["loc"]) == ("Needs Verification", "2026-11-20", "Paris")
    assert by["Old Utility Award"]["s"] == "Closed" and by["Old Utility Award"]["m"] == "Utility"
    assert by["Word Awards"]["det"] == "On your sheet: Anticipated March 2027" and by["Word Awards"]["dl"] == ""
    for n in ("New Awards", "Old Utility Award", "Word Awards"):
        d = by[n]
        assert d["prov"] is False and d["chk"] == "" and d["c"] == "" and d["dead"] is False and d["evdead"] is False and d["spon"] is False
    assert "(3 awaiting research)" in html and 'id="showawait"' in html and "Show <i>awaiting-research</i> rows (3)" in html
    assert 'id="awbox" style="display:block' in html and "(showAw || !r.aw)" in html and "Awaiting research" in html and SENTENCE.replace("week's", "week&#39;s") in html or SENTENCE in html
    assert len(data) == 4


def test_no_flag_or_no_such_rows_hides_the_second_checkbox_and_changes_nothing(tmp_path, monkeypatch):
    html, data, _ = _build(tmp_path, monkeypatch, flag=False)
    assert not any(d["aw"] for d in data) and 'id="awbox" style="display:none' in html and "awaiting research)" not in html.split("<span id=\"provnote\">")[1][:60]


def test_nothing_internal_is_on_the_awaiting_text_or_template():
    brp = _brp()
    chunks = [SENTENCE] + [ln for ln in brp.PAGE.splitlines() if "awbox" in ln or "showawait" in ln or "r.aw" in ln or "Awaiting" in ln or "awaiting" in ln]
    assert len(chunks) >= 5
    for c in chunks:
        low = c.lower()
        for w in ("queue", "tooling", "upstream", "canonical", "identity", "act-", "gate", "cost", "held", "id ", "deadline confirmed", "verified"):
            assert w not in low, (w, c)


def test_the_release_gate_counts_an_awaiting_row_as_on_the_page_with_an_information_reason(tmp_path):
    from test_release_gate import world, opts
    from scripts import release_gate as rg
    from test_release_gate import write
    w = world(tmp_path)
    extra = {"CONFERENCE": "Brand New Award", "EVENT_ID_CANON": "", "CONFERENCE URL": "https://n.example/", "SUBMISSION URL": "https://n.example/a/b", "START DATE": "", "Market": "Utility", "DUP_OF": ""}
    inp = w.md / "Awards_input.csv"
    import csv
    rows = list(csv.DictReader(open(inp, encoding="utf-8")))
    write(inp, rows + [extra], ["CONFERENCE", "EVENT_ID_CANON", "CONFERENCE URL", "SUBMISSION URL", "START DATE", "Market", "DUP_OF"])
    p = next((w.snaps / "utility-awards").glob("*.csv"))
    p.write_text(p.read_text(encoding="utf-8") + "Brand New Award,,,,,,https://n.example/a/b\n", encoding="utf-8")
    rep = rg.evaluate(opts(w, preflight=True))
    assert rep["counts"]["awaiting"] == 1
    st = rep["coverage"]["awards"]["utility-awards"]
    assert any(m["name"] == "Brand New Award" and m["on_page"] and m["reason"] == rg.R_QUEUED for m in st["missing"])
    b = next(c for c in rep["checks"] if c["id"] == "b")
    assert not any(r.startswith(("WARN", "FAIL")) and "Brand New Award" in r for r in b["rows"])
    assert any("Awaiting research" in x for x in rg.plain_lines(rep))
