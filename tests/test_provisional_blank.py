"""Held conference rows shown as Provisional with the FAILING FIELD BLANKED (ACT-70): every gate check's mapping, the default, the matching of a failure to a row, and the whole path from the
Saturday files to the page rows. Nothing here reads a live file or the network; the log lines are in the exact shape accept_delivery.py prints into weekend_import.log."""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import provisional_blank as pb                                 # noqa: E402
from scripts import provisional_rows as pr                                  # noqa: E402

ON = date(2026, 10, 12)
RULES = pb.load_rules()

# the checks and titles exactly as the gate prints them (weekend/20261010-230054/Cybersecurity_audited.candidate.gate.json); the date in check 6 and the field count in check 1 vary
GATE_CHECKS = {
    "1": "RFC 4180 - every row parses to the header's 45 fields", "2": "Cited pages resolve (404/410 = fail, 403 allowed unless a browser gets 404)",
    "3": "Cited page contains its quote verbatim (403 exempt)", "4": "No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)",
    "5": "No Exhibiting/Registration row carrying a deadline", "5b": "OPPORTUNITY_TYPE is one of the four enum values",
    "6": "No past deadline presented as open (as of 2026-10-10; rolling forms exempt)", "R8a": "GATED_STATUS and ISSUES left blank upstream",
    "R8b": "CITY holds a city, not a venue", "R8c": "EVENT_ID unique per row within a market", "R11": "GROUNDING_CONFIDENCE bound to IS_PROJECTED",
    "R2": "Future date marked verified only with a citation", "2.6": "No placeholder values where a real value belongs", "5.4": "No row representing a SERIES rather than one event",
    "6b": "Submission deadline precedes the event it feeds (Awards exempt)", "2.1b": "No discontinued event claiming a verified edition", "R8d": "EDITION is a plain 4-digit year",
    "R12": "FORMAT is In-Person, Virtual, Hybrid or blank", "R16": "An ASSERTED discontinuation carries its own evidence", "R18a": "SPONSOR_REQUIRED is Yes, No, Unknown or blank",
    "R18b": "A sponsorship requirement carries its own evidence", "R22": "Citations come from an admissible source", "R22b": "URLs point at a page, not a form endpoint or an API",
}

LOG = """\
[Cybersecurity] pinned rows: 1 ruling(s) held
$ accept_delivery.py X\\Cybersecurity_audited.candidate.csv --json X.json  -> exit 1 (233s)

==========================================================================
ACCEPTANCE GATE - Cybersecurity_audited.candidate.csv  (132 rows)
==========================================================================
  [PASS] 1    RFC 4180 - every row parses to the header's 45 fields
  [FAIL] 2    Cited pages resolve (404/410 = fail, 403 allowed unless a browser gets 404)  (2)
           - AI Summit New York: HTTP 404 https://newyork.theaisummit.com/submit-a-speaker
           - AppSec & DevSecOps (Corinium) Singapore: HTTP 404 https://www.coriniumintelligence.com/ciso-executive-network/request-to-speak
  [FAIL] 3    Cited page contains its quote verbatim (403 exempt)  (2)
           - GITEX Global: quote and date both absent - "Nov 2. Final Deadline."
           - AppWorld (MWC Mobile World Congress 2027: paraphrase, date IS on page - "Complete your submission by 5 November 2026 (23:00 C"
  [FAIL] 4    No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)  (2)
           - CDAO Fall: The event is confirmed for October 26-27, 2026, at the Renaissance Bos
           - AppSec & DevSecOps (Corinium): The 2027 edition of AppSec & DevSecOps Sydney is confirmed for Februar
  [FAIL] R8b  CITY holds a city, not a venue  (1)
           - GITEX Global: CITY='Expo City Dubai'
  [FAIL] 2.6  No placeholder values where a real value belongs  (2)
           - The Official Cybersecurity Summit: CITY='To Be Announced'
           - The Official Cybersecurity Summit: LOCATION='To Be Announced'
  [NOTE] 2s   SUBMISSION link returns 404/410 on a LIVE call - advisory  (1)
           - Some Approved Conference: SUBMISSION URL HTTP 404 https://x.example/a

  RESULT: REJECTED

ACCEPTANCE GATE - Utility_audited.candidate.csv  (90 rows)
  [FAIL] 4    No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)  (1)
           - Utility Only Conference: The event is confirmed for X
  RESULT: REJECTED
"""


def row(name, eid="", market="Cybersecurity", **kw):
    r = {c: "" for c in ("EVENT_ID", "CONFERENCE", "Market", "OPPORTUNITY_TYPE", "STATUS", "SUBMISSION DEADLINE", "START DATE", "CONFERENCE DATES", "CITY", "STATE_PROVINCE", "COUNTRY", "LOCATION",
                         "FORMAT", "GROUNDING_CONFIDENCE", "IS_PROJECTED", "STATUS DETAILS", "SUBMISSION URL", "CFP_SUBMISSION_URL", "CONFERENCE URL", "DEADLINE_QUOTE", "DEADLINE_EVIDENCE_URL", "ORGANIZER",
                         "TRACK", "EDITION", "SPONSOR_REQUIRED", "GATED_STATUS")}
    r.update({"EVENT_ID": eid or "2027-" + name.lower().replace(" ", "-"), "CONFERENCE": name, "Market": market, "OPPORTUNITY_TYPE": "Speaking", "STATUS": "Open", "SUBMISSION DEADLINE": "2026-12-01",
              "CONFERENCE URL": "https://" + name.split()[0].lower() + ".example/", "SUBMISSION URL": "https://" + name.split()[0].lower() + ".example/cfp", "DEADLINE_QUOTE": "Deadline 1 Dec",
              "DEADLINE_EVIDENCE_URL": "https://" + name.split()[0].lower() + ".example/cfp", "STATUS DETAILS": "The CFP closes on 1 December.", "IS_PROJECTED": "true", "CITY": "London"})
    r.update(kw)
    return r


# ------------------------------------------------------------------ the mapping file itself
def test_every_gate_check_has_a_mapping_with_the_gates_own_title_or_the_default():
    maps = RULES["gate_checks"]
    assert set(maps) == set(GATE_CHECKS), "a gate check without a rule (or a rule for a check the gate does not have) is a hole"
    for cid, title in GATE_CHECKS.items():
        m = maps[cid]
        assert m.get("use_default") or "blank" in m, cid
        # the title in the rule file is the gate's text (the varying parts aside): it is what a person reads to check the mapping
        assert m["title"].split(" (")[0].split(" - ")[0][:25] == title.split(" (")[0].split(" - ")[0][:25], (cid, m["title"], title)


def test_the_default_blanks_the_deadline_the_status_details_and_the_submission_link_and_keeps_the_rest():
    d = RULES["default"]
    assert {"SUBMISSION DEADLINE", "STATUS DETAILS", "SUBMISSION URL", "CFP_SUBMISSION_URL"} <= set(d["blank"])
    for kept in ("CONFERENCE", "START DATE", "CONFERENCE DATES", "CITY", "STATE_PROVINCE", "COUNTRY", "CONFERENCE URL", "MAIN_INFO_URL"):
        assert kept not in d["blank"]
    assert d["status"] == "Needs Verification"


# ------------------------------------------------------------------ reading the gate's words
def test_parse_log_reads_only_the_fail_blocks_of_the_named_market():
    fs = pb.parse_log(LOG, "Cybersecurity")
    assert [(f["check"], f["text"].split(":")[0]) for f in fs] == [
        ("2", "AI Summit New York"), ("2", "AppSec & DevSecOps (Corinium) Singapore"), ("3", "GITEX Global"), ("3", "AppWorld (MWC Mobile World Congress 2027"),
        ("4", "CDAO Fall"), ("4", "AppSec & DevSecOps (Corinium)"), ("R8b", "GITEX Global"), ("2.6", "The Official Cybersecurity Summit"), ("2.6", "The Official Cybersecurity Summit")]
    assert not any("Some Approved" in f["text"] for f in fs), "a NOTE block is advisory and holds nothing"
    assert [f["check"] for f in pb.parse_log(LOG, "Utility")] == ["4"]


def test_parse_gate_json_skips_passed_checks_and_the_no_network_skips():
    data = {"Cybersecurity_audited.candidate.csv": [{"check": "R8b", "name": "CITY holds a city, not a venue", "passed": False, "failures": ["X Summit: CITY='Hall 4'"]},
                                                    {"check": "2", "name": "Cited pages resolve", "passed": False, "failures": ["SKIPPED - --no-network"]},
                                                    {"check": "1", "name": "RFC", "passed": True, "failures": []}]}
    got = pb.parse_gate_json(data, "Cybersecurity")
    assert [(f["check"], f["text"]) for f in got] == [("R8b", "X Summit: CITY='Hall 4'")]
    assert pb.parse_gate_json(data, "Utility") == []


def test_held_rows_keyed_by_permanent_id_carry_a_gate_failure_or_a_row_rule_reason():
    txt = ("2027-a-b  # AUTO 2026-10-10 weekend_import - held back from this week's file by the row rule: [3] A B Conference: quote and date both absent - \"x\"\n"
           "2027-c-d  # AUTO 2026-10-10 weekend_import - held back from this week's file by the row rule: year check: Y1 START DATE 2027-04-12 is not in edition 2026\n"
           "2027-e-f  # AUTO 2026-10-02 weekend_import - new row from upstream\n# comment  # held back from this week's file by the row rule: nope\n")
    fs = pb.parse_held_rows(txt)
    assert [(f["check"], f["canon"]) for f in fs] == [("3", "2027-a-b"), ("row-rule", "2027-c-d")]


# ------------------------------------------------------------------ each mapping, on a row
def blank(r, check, text):
    f = pb.Failure(check, GATE_CHECKS.get(check, ""), text, "test")
    return pb.apply_blanks(r, [f], RULES)


def test_a_venue_in_city_blanks_city_only():
    r, done, _ = blank(row("GITEX Global", CITY="Expo City Dubai", COUNTRY="UAE"), "R8b", "GITEX Global: CITY='Expo City Dubai'")
    assert done == ["CITY"] and r["CITY"] == "" and r["COUNTRY"] == "UAE" and r["SUBMISSION DEADLINE"] == "2026-12-01" and r["STATUS"] == "Open"


def test_a_placeholder_blanks_the_field_it_names():
    r, done, _ = blank(row("X Summit", CITY="To Be Announced", LOCATION="To Be Announced"), "2.6", "X Summit: LOCATION='To Be Announced'")
    assert done == ["LOCATION"] and r["LOCATION"] == "" and r["CITY"] == "To Be Announced", "only the named field; the CITY failure line blanks CITY separately"
    r2, done2, _ = blank(row("X Summit", CITY="To Be Announced"), "2.6", "X Summit: CITY='To Be Announced'")
    assert done2 == ["CITY"]


def test_active_call_prose_on_a_projected_row_blanks_status_details_and_shows_needs_verification():
    r, done, _ = blank(row("CDAO Fall"), "4", "CDAO Fall: The event is confirmed for October 26-27, 2026, at the Renaissance Bos")
    assert done == ["STATUS DETAILS"] and r["STATUS DETAILS"] == "" and r["STATUS"] == "Needs Verification" and r["SUBMISSION DEADLINE"] == "2026-12-01"


def test_a_404_link_blanks_exactly_the_link_that_is_dead_and_nothing_else():
    r = row("AI Summit", **{"CFP_SUBMISSION_URL": "https://ai.example/submit-a-speaker", "DEADLINE_EVIDENCE_URL": "https://ai.example/evidence"})
    out, done, _ = blank(r, "2", "AI Summit: HTTP 404 https://ai.example/submit-a-speaker")
    assert done == ["CFP_SUBMISSION_URL"] and out["DEADLINE_EVIDENCE_URL"] == "https://ai.example/evidence" and out["SUBMISSION URL"] == r["SUBMISSION URL"] and out["STATUS"] == "Open"
    out2, done2, _ = blank(r, "2", "AI Summit: HTTP 404 (plain fetch said 403; a browser says 404) https://ai.example/evidence/")
    assert done2 == ["DEADLINE_EVIDENCE_URL"], "the match ignores a trailing slash"


def test_a_404_link_that_is_none_of_the_rows_fields_blanks_the_three_link_fields():
    out, done, _ = blank(row("AI Summit"), "2", "AI Summit: HTTP 404 https://elsewhere.example/gone")
    assert set(done) == {"SUBMISSION URL", "DEADLINE_EVIDENCE_URL"} and out["CONFERENCE URL"].startswith("https://ai"), "the website is kept"


def test_quote_and_date_absent_or_paraphrase_blanks_the_deadline_and_its_proof_and_shows_needs_verification():
    for text in ("GITEX Global: quote and date both absent - \"Nov 2. Final Deadline.\"", "GITEX Global: paraphrase, date IS on page - \"Complete by 5 Nov\""):
        r, done, _ = blank(row("GITEX Global"), "3", text)
        assert set(done) == {"SUBMISSION DEADLINE", "DEADLINE_QUOTE", "DEADLINE_EVIDENCE_URL", "STATUS DETAILS"} and r["STATUS"] == "Needs Verification" and r["STATUS DETAILS"] == "", "the prose restates the unproven deadline"


def test_every_mapped_check_blanks_what_its_rule_says(monkeypatch):
    for cid, rule in RULES["gate_checks"].items():
        if rule.get("use_default") or any(t.startswith("@") for t in rule["blank"]):
            continue
        base = row("Whole Row", **{f: "value" for f in rule["blank"] if f not in ("SUBMISSION DEADLINE",)})
        out, done, _ = blank(base, cid, "Whole Row: something")
        for f in rule["blank"]:
            assert out[f] == "" if f in out else True, (cid, f)
        assert set(done) <= set(rule["blank"]), cid
        assert out["CONFERENCE"] == "Whole Row" and out["CONFERENCE URL"] == base["CONFERENCE URL"], (cid, "the name and the website are never blanked by a mapped check")


def test_a_check_with_no_mapping_and_a_row_with_no_gate_result_both_take_the_default():
    full = row("Odd Row", **{f: "v" for f in RULES["default"]["blank"]})
    r, done, _ = blank(full, "R99", "Odd Row: new check nobody mapped")
    assert set(done) == set(RULES["default"]["blank"]) and r["STATUS"] == "Needs Verification" and r["CITY"] == "London" and r["CONFERENCE URL"].startswith("https://odd")
    r2, done2, why = pb.apply_blanks(full, [], RULES, checked=False)
    assert set(done2) == set(RULES["default"]["blank"]) and r2["STATUS"] == "Needs Verification" and "no gate result" in why[0]
    r3, done3, _ = blank(full, "5.4", "Odd Row: series")
    assert set(done3) == set(RULES["default"]["blank"]), "a check marked use_default takes the default"


def test_row_rule_reasons_year_check_blanks_the_dates_and_an_id_wait_blanks_nothing():
    y = pb.Failure("row-rule", "", "year check: Y1 START DATE 2027-04-12 is not in edition 2026", "held_rows.txt", canon="c")
    r, done, _ = pb.apply_blanks(row("Y Conf", **{"START DATE": "2027-04-12", "CONFERENCE DATES": "April 2026"}), [y], RULES)
    assert done == ["START DATE", "CONFERENCE DATES"] and r["STATUS"] == "Needs Verification"
    w = pb.Failure("row-rule", "", "no permanent id - cannot tell for certain which event this is", "held_rows.txt", canon="c")
    r2, done2, _ = pb.apply_blanks(row("W Conf"), [w], RULES)
    assert done2 == [] and r2["SUBMISSION DEADLINE"] == "2026-12-01" and r2["STATUS"] == "Open"
    z = pb.Failure("row-rule", "", "a brand new reason", "held_rows.txt", canon="c")
    assert set(pb.apply_blanks(row("Z Conf", **{f: "v" for f in RULES["default"]["blank"]}), [z], RULES)[1]) == set(RULES["default"]["blank"])


def test_several_failures_union_their_fields():
    fs = [pb.Failure("R8b", "", "G: CITY='Expo City'", "t"), pb.Failure("3", "", "G: quote and date both absent - \"x\"", "t")]
    r, done, why = pb.apply_blanks(row("G Global", CITY="Expo City"), fs, RULES)
    assert set(done) == {"CITY", "SUBMISSION DEADLINE", "DEADLINE_QUOTE", "DEADLINE_EVIDENCE_URL", "STATUS DETAILS"} and len(why) == 2 and r["STATUS"] == "Needs Verification"


# ------------------------------------------------------------------ matching a failure to a row
def test_a_failure_goes_to_the_longest_matching_name_and_to_the_row_with_the_value_it_names():
    rows = [row("AppSec & DevSecOps (Corinium)"), row("AppSec & DevSecOps (Corinium) Singapore", **{"CFP_SUBMISSION_URL": "https://www.coriniumintelligence.com/ciso-executive-network/request-to-speak"})]
    f = pb.Failure("2", "", "AppSec & DevSecOps (Corinium) Singapore: HTTP 404 https://www.coriniumintelligence.com/ciso-executive-network/request-to-speak", "t")
    assert pb.match_rows(f, rows) == [1]
    g = pb.Failure("4", "", "AppSec & DevSecOps (Corinium): The 2027 edition of AppSec & DevSecOps Sydney is confirmed", "t")
    assert pb.match_rows(g, rows) == [0], "the shorter name is not taken by the longer row"


def test_rows_that_share_a_cut_name_are_told_apart_by_the_value_the_failure_names():
    long = "Gartner Security & Risk Management Summit"
    rows = [row(long + " (London)", **{"SUBMISSION URL": "https://g.example/london"}), row(long + " (Tokyo)", **{"SUBMISSION URL": "https://g.example/tokyo"})]
    f = pb.Failure("2", "", long[:38] + ": SUBMISSION URL HTTP 404 https://g.example/tokyo", "t")
    assert pb.match_rows(f, rows) == [1]
    nothing_named = pb.Failure("4", "", long[:38] + ": prose", "t")
    assert pb.match_rows(nothing_named, rows) == [0, 1], "no value to tell them apart by: both are taken (the weekend importer's greedy rule)"


def test_a_permanent_id_keyed_reason_matches_by_the_permanent_id_only():
    rows = [row("Same Name", eid="up-1"), row("Same Name", eid="up-2")]
    f = pb.Failure("3", "", "Same Name: quote and date both absent", "held_rows.txt", canon="perm-2")
    assert pb.match_rows(f, rows, canon_of=lambda r: {"up-1": "perm-1", "up-2": "perm-2"}[r["EVENT_ID"]]) == [1]


# ------------------------------------------------------------------ the whole path
def _write(path: Path, rows, cols=None):
    cols = cols or list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def make_world(tmp_path: Path):
    md = tmp_path / "Markets"
    md.mkdir()
    data = tmp_path / "data"
    (data / "market_sheets").mkdir(parents=True)
    approved = [row("Approved Conf", eid="up-approved", **{"Market": "Cybersecurity"})]
    raw = [row("Approved Conf", eid="up-approved-new"),
           row("CDAO Fall", eid="up-cdao", **{"STATUS DETAILS": "The event is confirmed for October 26-27, 2026, at the Renaissance Boston"}),
           row("GITEX Global", eid="up-gitex", CITY="Expo City Dubai", **{"SUBMISSION DEADLINE": "2026-11-02", "DEADLINE_QUOTE": "Nov 2. Final Deadline."}),
           row("Silent Summit", eid="up-silent", **{"SUBMISSION DEADLINE": "2026-10-01", "STATUS": "Open"}),
           row("Stub Summit", eid="up-stub", **{"STATUS DETAILS": "Audit Exception: every attempt failed"})]
    _write(md / "Cybersecurity_audited.final.csv", approved)
    _write(md / "Cybersecurity_audited.csv", raw)
    stamp = datetime(2026, 10, 10, 15, 34).timestamp()
    os.utime(md / "Cybersecurity_audited.csv", (stamp, stamp))                      # the research of Saturday 2026-10-10; the import folder below is from that evening
    _write(md / "Cybersecurity_audited.identity.csv", [{"OUTPUT_EVENT_ID": r["EVENT_ID"], "OUTPUT_CONFERENCE": r["CONFERENCE"], "INPUT_CONFERENCE": r["CONFERENCE"],
                                                      "EVENT_ID_CANON": {"up-approved-new": "perm-approved"}.get(r["EVENT_ID"], "perm-" + r["EVENT_ID"])} for r in raw])
    wk = md / "weekend" / "20261010-230054"
    wk.mkdir(parents=True)
    (wk / "weekend_import.log").write_text(LOG.replace("AI Summit New York", "Unrelated").replace("GITEX Global: CITY", "GITEX Global: CITY"), encoding="utf-8")
    return md, data, approved


def test_conference_page_rows_end_to_end(tmp_path):
    md, data, approved = make_world(tmp_path)
    rows, report, msg = pr.conference_page_rows(md, "Cybersecurity", approved, {"up-approved": "perm-approved"}, ON, data_root=data)
    by = {r["CONFERENCE"]: r for r in rows}
    assert sorted(by) == ["CDAO Fall", "GITEX Global", "Silent Summit"], "the approved row and the stub are not provisional"
    assert all(r["_PROVISIONAL"] == "1" and r["GROUNDING_CONFIDENCE"] == "" and r["IS_PROJECTED"] == "" for r in rows)
    cd, gx, si = by["CDAO Fall"], by["GITEX Global"], by["Silent Summit"]
    assert cd["STATUS DETAILS"] == "" and cd["STATUS"] == "Needs Verification" and cd["_BLANKED"] == "STATUS DETAILS"
    assert gx["CITY"] == "" and gx["SUBMISSION DEADLINE"] == "" and gx["DEADLINE_QUOTE"] == "" and gx["STATUS"] == "Needs Verification"
    assert "Expo City Dubai" not in json.dumps(gx) and "Final Deadline" not in json.dumps(gx), "no known-bad value is left anywhere on the row"
    # a row no gate result names takes the default, and an Open status never survives
    assert si["SUBMISSION DEADLINE"] == "" and si["STATUS"] == "Needs Verification" and si["STATUS DETAILS"] == ""
    assert [e["checked"] for e in report if e["name"] == "Silent Summit"] == [False] and "kept" not in msg
    assert all(r["STATUS"] != "Open" or r["SUBMISSION DEADLINE"] >= "2026-10-12" for r in rows), "never an Open row past its deadline"
    assert all(r["CONFERENCE URL"] and r["CITY"] != "x" for r in rows) and gx["CONFERENCE URL"].startswith("https://gitex")


def test_a_candidate_with_the_name_of_an_approved_row_is_left_out(tmp_path):
    md, data, approved = make_world(tmp_path)
    raw = pr.read_csv(md / "Cybersecurity_audited.csv")
    raw.append(row("Approved Conf", eid="up-renamed"))
    _write(md / "Cybersecurity_audited.csv", raw)
    stamp = datetime(2026, 10, 10, 15, 34).timestamp()
    os.utime(md / "Cybersecurity_audited.csv", (stamp, stamp))
    ident = pr.read_csv(md / "Cybersecurity_audited.identity.csv") + [{"OUTPUT_EVENT_ID": "up-renamed", "OUTPUT_CONFERENCE": "Approved Conf", "INPUT_CONFERENCE": "Approved Conf", "EVENT_ID_CANON": "perm-other"}]
    _write(md / "Cybersecurity_audited.identity.csv", ident)
    rows, _rep, msg = pr.conference_page_rows(md, "Cybersecurity", approved, {"up-approved": "perm-approved"}, ON, data_root=data)
    assert "Approved Conf" not in [r["CONFERENCE"] for r in rows] and "same name" in msg


def test_no_research_this_cycle_shows_nothing(tmp_path):
    rows, report, msg = pr.conference_page_rows(tmp_path / "empty", "Cybersecurity", [], {}, ON)
    assert rows == [] and report == [] and "no raw research" in msg


# ------------------------------------------------------------------ the page
def test_the_conference_page_shows_the_held_rows_provisional_with_blanks_and_a_header_count(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("brp70", ROOT / "scripts" / "build_review_page.py")
    brp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brp)
    from src.cfp_monitor import identity
    md, data, approved = make_world(tmp_path)
    db = data / "cfp_monitor.db"
    db.write_bytes(b"")
    monkeypatch.setattr(identity, "seed_map", lambda p: ({"up-approved": "perm-approved"}, []))
    out = tmp_path / "Conference Review 2026-10-12 - Live Markets.html"
    monkeypatch.setattr(sys, "argv", ["build_review_page.py", "-i", str(md / "Cybersecurity_audited.final.csv"), "-o", str(out), "--kind", "conference", "--no-evidence",
                                      "--date", "2026-10-12", "--db", str(db), "--markets", "Cybersecurity,Utility", "--provisional-dir", str(md)])
    brp.main()
    html = out.read_text(encoding="utf-8")
    data_rows = json.JSONDecoder().raw_decode(html[html.index("const DATA = ") + len("const DATA = "):])[0]
    by = {d["n"]: d for d in data_rows}
    assert sorted(n for n, d in by.items() if d["prov"]) == ["CDAO Fall", "GITEX Global", "Silent Summit"] and by["Approved Conf"]["prov"] is False
    assert "(3 provisional)" in html and "Show <i>Provisional</i> rows (3)" in html and "Researched this week; our final checks are still running." in html
    for d in data_rows:
        if d["prov"]:
            assert d["chk"] == "" and d["c"] == "", "no verdict badge, no confidence"
            assert d["s"] != "Open" or d["dl"] >= "2026-10-12", "never an Open row past its deadline"
    g = by["GITEX Global"]
    assert g["loc"] == "" and g["dl"] == "" and g["q"] == "" and g["s"] == "Needs Verification" and by["CDAO Fall"]["det"] == ""
    assert "Expo City Dubai" not in html and "Nov 2. Final Deadline." not in html
    side = json.loads(out.with_suffix(".provisional.json").read_text(encoding="utf-8"))
    assert set({e["name"]: e["blanked"] for e in side["rows"]}["GITEX Global"]) >= {"CITY", "SUBMISSION DEADLINE", "DEADLINE_QUOTE", "DEADLINE_EVIDENCE_URL"}
    assert "provisional.json" not in html and "DEADLINE_QUOTE" not in html, "the field names stay out of the customer's page"


def test_the_provisional_text_and_template_carry_no_internal_words():
    import importlib.util
    spec = importlib.util.spec_from_file_location("brp70b", ROOT / "scripts" / "build_review_page.py")
    brp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brp)
    for chunk in [pr.SENTENCE] + [ln for ln in brp.PAGE.splitlines() if "prov" in ln.lower()]:
        for word in ("tooling", "upstream", "canonical", "identity", "ACT-", "held", "gate", "blank", "Deadline confirmed", "row rule", "check "):
            assert word.lower() not in chunk.lower() or word == "Deadline confirmed" and False, (word, chunk)
    assert "Deadline confirmed" not in pr.SENTENCE


def test_the_awards_page_header_names_the_real_markets_not_eight(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("brp70c", ROOT / "scripts" / "build_review_page.py")
    brp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brp)
    src = tmp_path / "in.csv"
    src.write_text("EVENT_ID,CONFERENCE,Market,OPPORTUNITY_TYPE\na,Alpha Awards,Utility,Awards\nb,Beta Awards,Cybersecurity,Awards\n", encoding="utf-8")
    snaps = tmp_path / "snaps"
    snaps.mkdir()
    out = tmp_path / "Awards.html"
    monkeypatch.setattr(sys, "argv", ["build_review_page.py", "-i", str(src), "-o", str(out), "--kind", "awards", "--no-evidence", "--date", "2026-10-12", "--customer-awards-dir", str(snaps)])
    brp.main()
    html = out.read_text(encoding="utf-8")
    assert "8 markets" not in html and "Cybersecurity + Utility" in html


def test_a_status_set_because_a_field_was_blanked_is_not_re_derived_from_the_dates_we_no_longer_trust():
    import importlib.util
    spec = importlib.util.spec_from_file_location("brp70d", ROOT / "scripts" / "build_review_page.py")
    brp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(brp)
    r = {c: "" for c in brp.FIELDS}
    r.update({"EVENT_ID": "x", "CONFERENCE": "Year Conf 2026", "Market": "Utility", "STATUS": "Needs Verification", "SUBMISSION DEADLINE": "2026-10-27", "_PROVISIONAL": "1"})
    assert brp.build([r], "2026-10-12")[0]["s"] == "Needs Verification"
    r2 = dict(r, STATUS="Open", **{"SUBMISSION DEADLINE": "2026-10-01"})
    assert brp.build([r2], "2026-10-12")[0]["s"] == "Closed", "an Open provisional row past its deadline is never shown Open"
