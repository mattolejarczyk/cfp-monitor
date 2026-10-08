"""ACT-54: the customer's row is the question. FIXTURES ONLY (throwaway databases and files in tmp_path; nothing live is read or written).

Worked example everywhere: Hack In The Box. The customer tracks conference.hitb.org, Alila SCBD, Jakarta, 29 Apr 2026. We held a Phuket event of 24 Aug 2026 on the same
website. The matcher called the exact URL 100 percent; it must now list the pair as DISAGREES and not certify it.

(b) link_agreement + match_customer_sheet + apply_client_match + customer_coverage    (c) context_text / page_wording / context_rows
(d) customer_row_answers.answers                                                       (e) schedule_only + accept_delivery R16c + check_schedule_status
"""
import csv
import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from scripts import customer_coverage as cc                       # noqa: E402
from scripts import customer_row_answers as cra                   # noqa: E402
from scripts import check_schedule_status as css                  # noqa: E402
from src.cfp_monitor import link_agreement as la                  # noqa: E402
from src.cfp_monitor import schedule_only as so                   # noqa: E402
from test_customer_coverage import make_world                     # noqa: E402

TODAY = "2026-10-08"
PHUKET = {"event_id": "2026-hack-in-the-box-phuket", "name": "Hack In The Box Security Conference 2026 - Phuket", "url": "https://conference.hitb.org/", "city": "Phuket",
          "start_date": "2026-08-24"}


# ----------------------------------------------------------------------------------------- (b) the rule
def test_hitb_pair_disagrees_on_both_date_and_place():
    why = la.link_disagreement("Alila SCBD, Jakarta, Indonesia", "04/29/2026", "Phuket", "2026-08-24")
    assert "date:" in why and "117 days apart" in why and "place:" in why and "Phuket" in why


def test_close_dates_and_a_city_named_in_the_venue_line_agree():
    assert la.link_disagreement("Alila SCBD, Jakarta, Indonesia", "04/29/2026", "Jakarta", "2026-05-15") == ""
    assert la.link_disagreement("Jakarta", "2026-04-29", "South Jakarta", "2026-04-29") == ""


def test_thirty_days_is_allowed_and_thirty_one_is_not():
    assert la.link_disagreement("", "2026-04-01", "", "2026-05-01") == ""
    assert "date:" in la.link_disagreement("", "2026-04-01", "", "2026-05-02")


def test_a_missing_date_or_place_cannot_disagree_and_a_year_alone_is_not_a_date():
    assert la.link_disagreement("", "", "Phuket", "2026-08-24") == ""
    assert la.link_disagreement("Jakarta", "", "", "2026-08-24") == ""
    assert la.link_disagreement("", "2026", "", "2026-12-31") == ""                      # '2026' must not be read as 1 July
    assert la.full_date("2026") is None and la.full_date("04/29/2026").isoformat() == "2026-04-29"


# ----------------------------------------------------------------------------------------- (b) the matcher, end to end
SHEET = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "EVENT START DATE"]


def _match(tmp_path, ours, theirs):
    from src.cfp_monitor.storage import Store
    db = tmp_path / "t.db"
    Store(str(db)).db.close()
    con = sqlite3.connect(db)
    for eid, name, city, url, start in ours:
        con.execute("insert into grounding_facts (event_id, name, city, url, start_date) values (?,?,?,?,?)", (eid, name, city, url, start))
    con.commit()
    con.close()
    (tmp_path / "d.csv").write_text("EVENT_ID,START DATE,Market\n", encoding="utf-8")
    with open(tmp_path / "s.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(SHEET)
        w.writerows(theirs)
    out = tmp_path / "m.csv"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "match_customer_sheet.py"), "--sheet", str(tmp_path / "s.csv"), "--market", "Cybersecurity", "--db", str(db),
                        "--delivery", str(tmp_path / "d.csv"), "-o", str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    with open(out, encoding="utf-8-sig") as fh:
        return {r["CONFERENCE"]: r for r in csv.DictReader(fh)}, p.stdout


OURS = [(PHUKET["event_id"], PHUKET["name"], "Phuket", PHUKET["url"], "2026-08-24")]


def test_hitb_exact_url_is_not_certified_when_place_and_date_disagree(tmp_path):
    rows, out = _match(tmp_path, OURS, [["Hack In The Box", "https://conference.hitb.org", "Alila SCBD, Jakarta, Indonesia", "04/29/2026"]])
    r = rows["Hack In The Box"]
    assert int(r["Index_Confidence"].rstrip("%")) < 100                                    # lowered, so apply_client_match.py (certain = 100) never writes it
    assert 40 <= int(r["Index_Confidence"].rstrip("%")) <= 69                              # in the review band: listed for a person, not 'absent'
    assert r["Index_Justification"].startswith("DISAGREES") and "Phuket" in r["Index_Justification"] and "Jakarta" in r["Index_Justification"]
    assert "disagree on date or place (held back for review, never certain): 1" in out


def test_the_same_pair_with_agreeing_place_and_date_is_still_certain(tmp_path):
    rows, out = _match(tmp_path, OURS, [["Hack In The Box", "https://conference.hitb.org", "Patong, Phuket, Thailand", "08/24/2026"]])
    assert rows["Hack In The Box"]["Index_Confidence"] == "100%" and "DISAGREES" not in rows["Hack In The Box"]["Index_Justification"]
    assert "never certain): 0" in out


def test_a_customer_row_with_no_date_or_place_is_still_judged_on_the_url_alone(tmp_path):
    rows, _ = _match(tmp_path, OURS, [["Hack In The Box", "https://conference.hitb.org", "", ""]])
    assert rows["Hack In The Box"]["Index_Confidence"] == "100%"                           # nothing to disagree with: unchanged behaviour


def test_apply_client_match_does_not_write_a_disagreeing_link(tmp_path):
    from src.cfp_monitor import clients
    rows, _ = _match(tmp_path, OURS, [["Hack In The Box", "https://conference.hitb.org", "Alila SCBD, Jakarta, Indonesia", "04/29/2026"]])
    r = rows["Hack In The Box"]
    m = [{"their_name": "Hack In The Box", "event_id": r["EVENT_ID"], "confidence": float(r["Index_Confidence"].rstrip("%")), "justification": r["Index_Justification"]}]
    con = sqlite3.connect(tmp_path / "t.db")
    clients.ensure_schema(con)
    con.execute("insert into client_conferences (client_key, their_name, first_seen) values ('arnica','Hack In The Box','2026-10-08')")
    res = clients.apply_matches(con, "arnica", m)
    assert res["applied"] == 0 and res["needs_review"] == 1
    assert con.execute("select coalesce(event_id,'') from client_conferences").fetchone()[0] == ""


# ----------------------------------------------------------------------------------------- (b) revisit existing links
def _linked_db(tmp_path):
    db = tmp_path / "l.db"
    con = sqlite3.connect(db)
    con.execute("create table grounding_facts (event_id text, name text, url text, city text, start_date text)")
    con.execute("create table client_conferences (client_key text, their_name text, their_url text, location text, event_start_date text, event_id text, withdrawn_by_customer integer default 0)")
    con.execute("insert into grounding_facts values (?,?,?,?,?)", (PHUKET["event_id"], PHUKET["name"], PHUKET["url"], "Phuket", "2026-08-24"))
    con.execute("insert into grounding_facts values ('ok-1','Fine Conf','https://f.example','Berlin','2026-11-02')")
    con.execute("insert into client_conferences values ('arnica','Hack In The Box','https://conference.hitb.org','Alila SCBD, Jakarta, Indonesia','04/29/2026',?,0)", (PHUKET["event_id"],))
    con.execute("insert into client_conferences values ('arnica','Fine Conf','https://f.example','Berlin, Germany','11/02/2026','ok-1',0)")
    con.execute("insert into client_conferences values ('arnica','Gone','https://h.example','Jakarta','04/29/2026',?,1)", (PHUKET["event_id"],))
    con.commit()
    return con


def test_existing_links_are_revisited_read_only(tmp_path):
    con = _linked_db(tmp_path)
    bad = la.linked_disagreements(con, "arnica")
    assert [x["name"] for x in bad] == ["Hack In The Box"]                                 # agreeing and customer-withdrawn rows are not listed
    assert bad[0]["event_id"] == PHUKET["event_id"] and "Jakarta" in bad[0]["why"]
    assert con.execute("select count(*) from client_conferences").fetchone()[0] == 3        # nothing written


def test_customer_coverage_uses_the_same_rule(tmp_path):
    row = {"location": "Alila SCBD, Jakarta, Indonesia", "event_start_date": "04/29/2026", "withdrawn_by_customer": 0}
    assert "Phuket" in cc.disagreement(row, PHUKET, TODAY)
    assert cc.disagreement(row, {"city": "Jakarta", "start_date": "2026-04-29"}, TODAY) == ""


# ----------------------------------------------------------------------------------------- (c) research context and page wording
HITB_ROW = {"client_key": "arnica", "their_name": "Hack In The Box", "their_url": "https://conference.hitb.org", "location": "Alila SCBD, Jakarta, Indonesia",
            "event_start_date": "04/29/2026", "status": "Info Needed", "event_id": PHUKET["event_id"], "withdrawn_by_customer": 0}


def test_context_text_carries_name_url_place_date_and_not_the_customers_status():
    t = cra.context_text(HITB_ROW)
    for part in ("Hack In The Box", "https://conference.hitb.org", "Alila SCBD, Jakarta, Indonesia", "04/29/2026", "Arnica", "not evidence", "Your sheet says"):
        assert part in t
    assert "Info Needed" not in t


def test_page_wording_says_your_sheet_says_x_we_found_y():
    s = cra.page_wording(HITB_ROW, PHUKET)
    assert s.startswith("Your sheet says Alila SCBD, Jakarta, Indonesia, 04/29/2026; we found Phuket, 2026-08-24")
    assert cra.page_wording(HITB_ROW, {"city": "Jakarta", "start_date": "2026-04-29", "name": "x"}) == ""
    assert cra.page_wording(HITB_ROW, None) == ""


def test_context_rows_pair_by_id_or_url_and_date_and_leave_inputs_untouched():
    inputs = {"Cybersecurity": [{"CONFERENCE": "Hack In The Box Jakarta", "CONFERENCE URL": "https://conference.hitb.org/", "START DATE": "", "EVENT_ID_CANON": "", "DUP_OF": ""},
                                {"CONFERENCE": "Unrelated", "CONFERENCE URL": "https://u.example/", "START DATE": "", "EVENT_ID_CANON": "", "DUP_OF": ""},
                                {"CONFERENCE": "Phuket row", "CONFERENCE URL": "https://conference.hitb.org/", "START DATE": "2026-08-24", "EVENT_ID_CANON": "", "DUP_OF": ""}]}
    before = [dict(r) for r in inputs["Cybersecurity"]]
    out = cra.context_rows([HITB_ROW | {"event_id": ""}], inputs, {})
    assert [o["CONFERENCE"] for o in out] == ["Hack In The Box Jakarta"]                    # the dated Phuket row is 117 days away: same website is not the same event
    assert "Alila SCBD" in out[0]["CUSTOMER_ROW"] and inputs["Cybersecurity"] == before


# ----------------------------------------------------------------------------------------- (d) one line per customer row
def _answer_world(tmp_path):
    rows = [
        {"name": "Researched Conf", "event_id": "2026-researched", "url": "https://r.example/", "loc": "Berlin, Germany", "start": "11/02/2026"},
        {"name": "Hack In The Box", "event_id": PHUKET["event_id"], "url": "https://conference.hitb.org", "loc": "Alila SCBD, Jakarta, Indonesia", "start": "04/29/2026"},
        {"name": "Old Conf", "event_id": "2025-old-conf", "url": "https://old.example/", "loc": "Paris", "start": "03/01/2026"},
        {"name": "Older Conf", "event_id": "2025-older-conf", "url": "https://older.example/", "loc": "Rome", "start": "03/01/2026"},
        {"name": "Ruled Conf", "url": "https://ruled.example/", "start": "12/01/2026"},
        {"name": "Missing Conf", "url": "https://missing.example/", "start": "12/01/2026"},
    ]
    facts = [PHUKET,
             {"event_id": "2026-researched", "name": "Researched Conf", "url": "https://r.example/", "city": "Berlin", "start_date": "2026-11-02"},
             {"event_id": "2025-old-conf", "name": "Old Conf", "url": "https://old.example/", "city": "Paris", "start_date": "2026-03-01"},
             {"event_id": "2027-old-conf", "name": "Old Conf 2027", "url": "https://old.example/", "city": "Paris", "start_date": "2027-03-01"},
             {"event_id": "2025-older-conf", "name": "Older Conf", "url": "https://older.example/", "city": "Rome", "start_date": "2026-03-01"}]
    inputs = [{"CONFERENCE": "Researched Conf", "CONFERENCE URL": "https://r.example/", "EVENT_ID_CANON": "2026-researched"},
              {"CONFERENCE": "HITB Phuket", "CONFERENCE URL": "https://conference.hitb.org/", "EVENT_ID_CANON": PHUKET["event_id"]},
              {"CONFERENCE": "Ruled Conf", "CONFERENCE URL": "https://ruled.example/"}]
    ledger = [{"event_name": "Ruled Conf", "url": "", "client": "arnica", "reason": "not a speaking opportunity", "ruled_by": "Matt", "ruled_on": "2026-10-07"}]
    db, md, led = make_world(tmp_path, rows, inputs, facts=facts, ledger=ledger, seed=())
    con = sqlite3.connect(db)
    for col in ("status", "deadline", "verify_state", "imported_at"):
        con.execute(f"alter table grounding_facts add column {col} text")
    con.execute("update grounding_facts set status='Open', deadline='2026-12-01', verify_state='Verified on the page', imported_at='2026-10-03' where event_id='2026-researched'")
    con.commit()
    con.close()
    return db, md, led


def test_every_customer_row_gets_exactly_one_answer_and_a_reason(tmp_path):
    db, md, led = _answer_world(tmp_path)
    res, facts, rows, inputs, u2c, degraded = cra.load(db, md, led, TODAY)
    lines = cra.answers(res, facts, u2c, TODAY)
    by = {a["name"]: a for a in lines}
    assert len(lines) == len(rows) == 6 and all(a["reason"] for a in lines)
    assert by["Researched Conf"]["answer"] == "RESEARCHED" and "status Open" in by["Researched Conf"]["reason"] and "Verified on the page" in by["Researched Conf"]["reason"]
    assert by["Hack In The Box"]["answer"] == "DISAGREES"                                     # beats 'over': the customer's 29 Apr date is before today but the event is postponed, not over
    assert "Alila SCBD" in by["Hack In The Box"]["reason"] and "Phuket" in by["Hack In The Box"]["reason"] and "not certain" in by["Hack In The Box"]["reason"]
    assert by["Old Conf"]["answer"] == "OVER" and "2027-old-conf (2027-03-01)" in by["Old Conf"]["reason"]
    assert by["Older Conf"]["answer"] == "OVER" and "next edition not announced" in by["Older Conf"]["reason"]
    assert by["Ruled Conf"]["answer"] == "EXCLUDED (ruling)" and "not a speaking opportunity" in by["Ruled Conf"]["reason"] and "Matt" in by["Ruled Conf"]["reason"]
    assert by["Missing Conf"]["answer"] == "NO ANSWER"                                         # a gap is named, never silent
    line = cra.summary_line(lines)
    assert line == "CUSTOMER ROWS: 6 rows; 1 researched; 1 DISAGREE; 2 over; 1 excluded; 1 NO ANSWER"


def test_command_line_writes_the_internal_report_and_the_context_proposal_and_exits_zero(tmp_path):
    db, md, led = _answer_world(tmp_path)
    out = tmp_path / "qa"
    ctx = tmp_path / "ctx.csv"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "customer_row_answers.py"), "--today", TODAY, "--db", str(db), "--markets-dir", str(md), "--ledger", str(led),
                        "--out-dir", str(out), "--propose-context", str(ctx)], capture_output=True, text=True)
    assert p.returncode == 0 and "CUSTOMER ROWS: 6 rows" in p.stdout and "CUSTOMER ROWS NO ANSWER: Missing Conf" in p.stdout
    md_text = (out / "customer_rows.md").read_text(encoding="utf-8")
    assert "INTERNAL QA" in md_text and md_text.count("| arnica |") == 6
    assert (out / "customer_rows.json").exists()
    with open(ctx, encoding="utf-8", newline="") as fh:
        got = list(csv.DictReader(fh))
    assert {g["CONFERENCE"] for g in got} >= {"Researched Conf"} and all(g["CUSTOMER_ROW"].startswith("CUSTOMER ROW") for g in got)


def test_the_database_is_never_written_and_a_missing_database_is_unknown_not_a_crash(tmp_path):
    db, md, led = _answer_world(tmp_path)
    before = db.read_bytes()
    cra.load(db, md, led, TODAY)
    assert db.read_bytes() == before
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "customer_row_answers.py"), "--db", str(tmp_path / "nope.db"), "--out-dir", str(tmp_path / "o")], capture_output=True, text=True)
    assert p.returncode == 0 and "CUSTOMER ROWS: UNKNOWN" in p.stdout


# ----------------------------------------------------------------------------------------- (e) typical schedule is not a page
HITB_PUBLISHED = {"CONFERENCE": "Hack In The Box Security Conference 2026", "STATUS": "Closed",
                  "STATUS DETAILS": "The flagship Asian edition of HITB typically runs in late August in Thailand. As of September 19, 2026, the 2026 event and its call for papers have concluded "
                                    "based on the typical annual schedule and the absence of active 2026 listings on the official site."}
BILLINGTON = {"CONFERENCE": "Billington", "STATUS": "Closed",
              "STATUS DETAILS": "The summit took place from September 8-10, 2026. Official site messaging confirms completion. Speaker inquiries are typically handled via direct contact."}
ODSC = {"CONFERENCE": "ODSC East 2027", "STATUS": "Upcoming",
        "STATUS DETAILS": "ODSC East 2027 is scheduled to take place from May 10 to May 12, 2027. The website confirms the edition. Based on previous cycles, the CFP is expected to open in late 2026."}


def test_hitb_published_status_rests_only_on_the_schedule():
    bad, phrase = so.schedule_only(HITB_PUBLISHED)
    assert bad and phrase == "typically"
    assert so.find_schedule_only([HITB_PUBLISHED])[0]["proposed_status"] == "Needs Verification"


def test_rows_that_report_what_a_page_says_are_not_flagged():
    assert so.find_schedule_only([BILLINGTON, ODSC]) == []


def test_a_citation_pair_clears_it_and_a_half_pair_does_not():
    assert so.schedule_only(HITB_PUBLISHED | {"LIFECYCLE_EVIDENCE_URL": "https://x.example/p", "LIFECYCLE_QUOTE": "the 2026 event has concluded"})[0] is False
    assert so.schedule_only(HITB_PUBLISHED | {"DEADLINE_EVIDENCE_URL": "https://x.example/p", "DEADLINE_QUOTE": "closes 1 Aug"})[0] is False
    assert so.schedule_only(HITB_PUBLISHED | {"LIFECYCLE_EVIDENCE_URL": "https://x.example/p"})[0] is True


def test_needs_verification_is_never_flagged():
    assert so.schedule_only(HITB_PUBLISHED | {"STATUS": "Needs Verification"})[0] is False


def test_the_gate_reports_it_as_an_advisory_note_not_a_rejection(tmp_path):
    spec = importlib.util.spec_from_file_location("_ad_act54", ROOT / "scripts" / "accept_delivery.py")
    ad = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ad)
    cols = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE", "SPONSOR_URL", "SPONSOR_REQUIRED",
            "IS_PROJECTED", "GROUNDING_CONFIDENCE", "STATUS", "STATUS DETAILS"]
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerow({c: (HITB_PUBLISHED | {"EVENT_ID": "2026-hitb"}).get(c, "") for c in cols})
    g = ad.Gate(str(p), network=False)
    with open(p, encoding="utf-8-sig", newline="") as fh:
        g.rows = list(csv.DictReader(fh))
    g.check_schema_rules()
    notes = {n[0]: n for n in g.notes}
    assert "R16c" in notes and "Hack In The Box" in notes["R16c"][2][0] and "Needs Verification" in notes["R16c"][2][0]
    assert all(ok for num, _n, ok, _f in g.results if num == "R16c") and "R16c" not in [r[0] for r in g.results]


def test_check_schedule_status_lists_the_row_and_survives_a_missing_file(tmp_path):
    f = tmp_path / "Cybersecurity_audited.final.csv"
    with open(f, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["CONFERENCE", "STATUS", "STATUS DETAILS"])
        w.writeheader()
        w.writerows([{k: r[k] for k in ("CONFERENCE", "STATUS", "STATUS DETAILS")} for r in (HITB_PUBLISHED, BILLINGTON, ODSC)])
    found, missing = css.scan([f, tmp_path / "Utility_audited.final.csv"])
    assert [x["name"] for x in found] == ["Hack In The Box Security Conference 2026"] and len(missing) == 1
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_schedule_status.py"), "--markets-dir", str(tmp_path)], capture_output=True, text=True)
    assert p.returncode == 0 and "SCHEDULE-ONLY STATUS: 1 row(s)" in p.stdout and "DEGRADED" in p.stdout


def test_a_shared_place_word_agrees_but_a_venue_word_alone_does_not():
    assert la.place_agrees("ATI ONGC, Goa", "Grand Hyatt Goa") is True
    assert la.place_agrees("Gaylord Palms Resort, Orlando, Florida", "Kissimmee") is False        # still listed: a person decides
    assert la.place_agrees("Hilton Washington, Washington, D.C., USA", "Hilton Orlando") is False
    assert la.place_agrees("Alila SCBD, Jakarta, Indonesia", "Phuket") is False
