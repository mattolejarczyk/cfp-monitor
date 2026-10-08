

def test_saturday_recap_reports_what_the_load_check_flagged():
    from scripts.weekend_recap import load_qa_lines
    head, flags = load_qa_lines({"flags": ["RSA 2027: evidence page LOST", "x"], "cycle": "2026-10-05", "summary": "s"})
    assert "2 thing(s)" in head and flags[0].startswith("RSA")
    head, flags = load_qa_lines({"flags": [], "cycle": "2026-10-05", "summary": "all consistent"})
    assert "nothing we had proven was lost" in head and flags == []
    head, flags = load_qa_lines(None)
    assert "did not run" in head


# --- ACT-51: the COVERAGE line from the Saturday log ---
LOG_OK = "=== run_monthly exit code: 0 ===\nINTAKE HEALTH: ok\nCOVERAGE: 20 of 20 customer rows ahead of 2026-10-10 are in the research queue; 0 are NOT\n"
LOG_BAD = ("INTAKE HEALTH: ok\nCOVERAGE: 17 of 20 customer rows ahead of 2026-10-10 are in the research queue; 3 are NOT\n"
           "COVERAGE NOT IN QUEUE: Alpha Con; Beta Expo; Gamma Summit\n=== run_monthly exit code: 0 ===\n")


def test_parse_saturday_reads_the_coverage_line_and_names():
    from scripts.weekend_recap import parse_saturday
    c = parse_saturday(LOG_BAD)["coverage"]
    assert c["not_in"] == 3 and c["names"] == "Alpha Con; Beta Expo; Gamma Summit" and c["line"].startswith("17 of 20")
    assert parse_saturday(LOG_OK)["coverage"]["not_in"] == 0
    assert parse_saturday("no such line\n")["coverage"] is None
    assert parse_saturday("COVERAGE: UNKNOWN - database not found (x)\n")["coverage"]["not_in"] is None


def _recap(log, kind="saturday"):
    from pathlib import Path
    from scripts.weekend_recap import saturday_recap
    return saturday_recap(log, None, Path("."), kind, None)


def test_subject_carries_a_flag_and_the_body_the_names_when_rows_are_missing():
    subject, text, html_ = _recap(LOG_BAD)
    assert "FLAG: 3 customer row(s) not in the research queue" in subject
    assert "Alpha Con; Beta Expo; Gamma Summit" in text and "NOT in the research queue" in html_


def test_no_flag_when_every_row_is_in_the_queue_and_plain_note_when_unknown_or_absent():
    subject, text, _ = _recap(LOG_OK)
    assert "FLAG" not in subject and "20 of 20 customer rows" in text
    subject, text, _ = _recap("COVERAGE: UNKNOWN - database not found (x)\n")
    assert "FLAG" not in subject and "could not be checked" in text
    subject, text, _ = _recap("nothing\n")
    assert "FLAG" not in subject and "did not run this week" in text


def test_friday_awards_recap_has_no_customer_coverage_line():
    subject, text, _ = _recap(LOG_BAD, "friday")
    assert "FLAG" not in subject and "customer rows" not in text.lower()


def test_recap_mentions_linked_rows_that_disagree_without_flagging_the_subject():
    log = "COVERAGE: 20 of 20 customer rows ahead of 2026-10-10 are in the research queue; 0 are NOT; 4 linked rows disagree on date or place" + chr(10)
    subject, text, _ = _recap(log)
    assert "FLAG" not in subject and "4 customer row(s) are linked to an event that disagrees" in text


# --- ACT-58: upstream's promises in the Saturday recap ---
def test_commitment_facts_and_sentence_flag_a_broken_promise(tmp_path):
    from scripts.weekend_recap import commitment_facts, commitment_sentence, saturday_recap
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("id,promised_on,note,market,event_id,column,op,expected,due,what\n"
                      "C1,2026-10-05,38,Cybersecurity,evt-a,STATUS,equals,Open,2026-01-01,evt-a is Open\n", encoding="utf-8")
    md = tmp_path
    (md / "Cybersecurity_audited.final.csv").write_text("EVENT_ID,STATUS\nevt-a,Closed\n", encoding="utf-8")
    c = commitment_facts(md, ledger=ledger, db=tmp_path / "none.db")
    assert c["broken"] == 1 and c["kept"] == 0 and "C1 (note 38)" in c["broken_lines"][0]
    assert commitment_sentence(c).startswith("FLAG - Upstream's promises: 0 kept, 1 NOT kept")
    (md / "Cybersecurity_audited.final.csv").write_text("EVENT_ID,STATUS\nevt-a,Open\n", encoding="utf-8")
    ok = commitment_facts(md, ledger=ledger, db=tmp_path / "none.db")
    assert ok["broken"] == 0 and "FLAG" not in commitment_sentence(ok)
    assert "did not run" in commitment_sentence(None)
    subject, text, _ = saturday_recap(LOG_OK, None, md, "saturday", None, c)
    assert "1 upstream promise(s) NOT kept" in subject and "NOT kept" in text


# --- ACT-51 phase 2: the AUTOADD line ---
LOG_AUTO = ("COVERAGE: 17 of 20 customer rows ahead of 2026-10-10 are in the research queue; 3 are NOT\nCOVERAGE NOT IN QUEUE: Alpha Con; Beta Expo; Gamma Summit\n"
            "AUTOADD: mode=applied; 1 added, 2 held for a person, 4 waiting for an id; 2 customer rows NOT in the queue after the step\n"
            "AUTOADD HELD: Beta Expo; Gamma Summit\nAUTOADD NOT PICKED UP: Beta Expo; Gamma Summit\n")


def test_parse_saturday_reads_the_autoadd_lines():
    from scripts.weekend_recap import parse_saturday, autoadd_sentence
    a = parse_saturday(LOG_AUTO)["autoadd"]
    assert a["applied"] and a["held_names"] == "Beta Expo; Gamma Summit" and a["missed_names"] == "Beta Expo; Gamma Summit"
    assert autoadd_sentence(a).startswith("FLAG - customer rows added to the plan but NOT picked up: Beta Expo")
    assert parse_saturday(LOG_OK)["autoadd"] is None and autoadd_sentence(None) == ""
    u = parse_saturday("AUTOADD: UNKNOWN - coverage could not run (x)\n")["autoadd"]
    assert u["unknown"] and "could not run" in autoadd_sentence(u)
    d = parse_saturday("AUTOADD: mode=dry-run; 2 to add, 0 held for a person, 0 waiting for an id; 2 customer rows NOT in the queue after the step\n")["autoadd"]
    assert not d["missed_names"] and "FLAG" not in autoadd_sentence(d)
