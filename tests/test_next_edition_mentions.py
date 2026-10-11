"""ACT-33: scripts/next_edition_mentions.py lists ended Closed rows whose own text announces a next edition, and whether a successor row exists. Fixtures only; no network, no model."""
import csv
import sqlite3
from datetime import date

from scripts import next_edition_mentions as N

TODAY = date(2026, 10, 11)


def test_sentences_with_a_later_edition_and_a_date_are_found():
    assert N.mentions("The 2027 edition is already scheduled for April 13-15, 2027.", 2026)
    assert N.mentions("The next edition is scheduled for June 8-10, 2027.", 2026)
    assert N.mentions("Save the date: the event returns on 3 March 2027.", 2026)
    assert N.mentions("The next edition, DECARBON 2027, is scheduled for February 15-16, 2027, in Berlin.", 2026)


def test_sentences_about_the_event_that_ended_or_with_no_date_are_not_dated_mentions():
    assert N.mentions("The event took place from April 22-24, 2026, at the Mandalay Bay.", 2026) == []
    assert N.mentions("It returns to Marina Bay Sands with a four-day program.", 2026) == []
    assert N.mentions("The official site now promotes the 2027 edition.", 2026) == []                    # a later year, but no date: the second tier
    assert N.mentions("The official site now promotes the 2027 edition.", 2026, with_dates=False)
    assert N.mentions("The official website now indicates that 2027 dates and location are coming soon.", 2026, with_dates=False)
    assert N.mentions("The event took place in 2026.", 2026, with_dates=False) == []


def test_same_series_ignores_years_and_filler_but_not_the_place():
    assert N.same_series("Decarb Connect UK 2026", "Decarb Connect UK 2027")
    assert not N.same_series("Decarb Connect UK 2026", "Decarb Connect Europe 2027")
    assert N.same_series("Billington 17th Annual CyberSecurity Summit 2026", "Billington CyberSecurity Summit 2027")
    assert not N.same_series("SecureWorld Quantum Cryptography 2026", "SecureWorld Dallas 2026")


def _db(tmp_path):
    p = tmp_path / "c.db"
    con = sqlite3.connect(p)
    con.execute("create table grounding_facts (event_id, conference_key, name, start_date, key_year)")
    con.executemany("insert into grounding_facts values (?,?,?,?,?)", [
        ("2026-info", "info.org", "Info Europe 2026", "2026-06-02", "2026"), ("2027-info", "info.org", "Info Europe 2027", "2027-06-08", "2027"),
        ("2026-sw-q", "sw.io", "SecureWorld Quantum 2026", "2026-09-22", "2026"), ("2026-sw-d", "sw.io", "SecureWorld Dallas 2026", "2026-10-08", "2026"),
        ("2026-lone", "lone.org", "Lone Summit 2026", "2026-05-01", "2026")])
    con.commit()
    con.close()
    (tmp_path / "market_sheets").mkdir()
    return p


def _row(eid, name, dates, start, details, status="Closed"):
    return {"EVENT_ID": eid, "CONFERENCE": name, "STATUS": status, "CONFERENCE DATES": dates, "START DATE": start, "STATUS DETAILS": details, "NOTES": "", "OVERVIEW": "", "LIFECYCLE_QUOTE": ""}


def test_scan_reports_successors_by_series_not_by_host_and_skips_live_and_not_yet_ended_rows(tmp_path):
    db = _db(tmp_path)
    rows = [_row("2026-info", "Info Europe 2026", "June 2 - June 4, 2026", "2026-06-02", "The next edition is scheduled for June 8-10, 2027."),
            _row("2026-sw-q", "SecureWorld Quantum 2026", "September 22, 2026", "2026-09-22", "The next edition is scheduled for May 27, 2027."),
            _row("2026-lone", "Lone Summit 2026", "May 1, 2026", "2026-05-01", "The 2027 edition has been announced for May 4-5, 2027."),
            _row("2026-live", "Live Con 2026", "November 3, 2026", "2026-11-03", "The 2027 edition is scheduled for May 4, 2027.", status="Open"),
            _row("2026-future", "Future Con 2026", "December 3, 2026", "2026-12-03", "The 2027 edition is scheduled for May 4, 2027.")]
    found, ended = N.scan(rows, "Cybersecurity", TODAY, db, {})
    assert ended == 3                                                                                  # Open and not-yet-ended rows are not read
    by = {f["canonical"]: f for f in found}
    assert set(by) == {"2026-info", "2026-sw-q", "2026-lone"}
    assert [s["event_id"] for s in by["2026-info"]["successors"]] == ["2027-info"]
    assert by["2026-sw-q"]["successors"] == [] and by["2026-lone"]["successors"] == []                  # SecureWorld Dallas shares the host, not the series


def test_the_research_list_counts_as_a_place_the_next_edition_already_is(tmp_path):
    db = _db(tmp_path)
    rows = [_row("2026-lone", "Lone Summit 2026", "May 1, 2026", "2026-05-01", "The 2027 edition has been announced for May 4-5, 2027.")]
    found, _ = N.scan(rows, "Utility", TODAY, db, {}, [{"CONFERENCE": "Lone Summit 2027", "EVENT_ID_CANON": "2027-lone", "EDITION": "2027"}])
    assert found[0]["listed"] == ["Lone Summit 2027"]
    line, md = N.report(found, 1, TODAY)
    assert "0 of the 1 have no successor row" in line and "on the research list, not yet in the database: Lone Summit 2027" in md


def test_main_writes_the_report_and_never_raises(tmp_path, capsys):
    db = _db(tmp_path)
    md = tmp_path / "Markets"
    md.mkdir()
    with open(md / "Utility_audited.final.csv", "w", encoding="utf-8", newline="") as fh:
        rows = [_row("2026-lone", "Lone Summit 2026", "May 1, 2026", "2026-05-01", "The 2027 edition has been announced for May 4-5, 2027.")]
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    out = tmp_path / "out"
    assert N.main(["--today", "2026-10-11", "--markets-dir", str(md), "--db", str(db), "--out-dir", str(out)]) == 0
    assert "NEXT-EDITIONS: 1 of 1 ended Closed rows mention a next edition WITH dates" in capsys.readouterr().out
    assert (out / "next_editions.md").exists() and (out / "next_editions.csv").exists()
    assert N.main(["--today", "garbage", "--markets-dir", str(md), "--db", str(db), "--out-dir", str(out)]) == 0
    assert "UNKNOWN" in capsys.readouterr().out
