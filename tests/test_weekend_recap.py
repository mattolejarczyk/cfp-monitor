

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
