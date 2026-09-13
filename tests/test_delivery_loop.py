"""The hand-back loop's two judgement points, replayed on 2026-09-12's real cases, offline.

1. Turning gate failures into questions: a failure must land on the right row or on nobody.
2. Using upstream's answers: nothing is applied that the live page does not support, and no
   answer may change a claim (a date, a status) - those go to a person.
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import delivery_loop as dl                               # noqa: E402
from scripts import mechanical_repairs as mr                          # noqa: E402

TODAY = date(2026, 9, 12)
SECUREWORLD = ("Speaker Deadlines Schedule Twin Cities, MN 2026 2026-09-19 Twin Cities, MN 2026 "
               "2026-11-19 2026-11-19 East 2026 2026-10-04 East 2026 2026-11-18 2026-11-18")
FORM = "https://info.secureworld.io/speaker-submission-form"
EVENTS = "https://www.secureworld.io/events"
DEAD = "https://www.secureworld.io/call-for-speakers"


def row(**kw):
    base = {"CONFERENCE": "SecureWorld East 2026", "SUBMISSION DEADLINE": "2026-10-04",
            "IS_PROJECTED": "true", "GROUNDING_CONFIDENCE": "Projected (2026)", "STATUS": "Open",
            "STATUS DETAILS": "Speaker deadline October 4, 2026.", "NOTES": "theirs",
            "SUBMISSION URL": DEAD, "CFP_SUBMISSION_URL": "", "DEADLINE_EVIDENCE_URL": "",
            "DEADLINE_QUOTE": "", "CONFERENCE DATES": "November 18, 2026"}
    base.update(kw)
    return base


def fetch(table):
    return lambda url: table.get(url, (200, ""))


def browser(dead):
    return lambda urls: {u for u in urls if u in dead}


def answers(conference, *items):
    return {"rows": [{"conference": conference, "issues": [], "answers": list(items)}]}


def ans(disposition, field="", url="", quote="", changes=None, explanation=""):
    return {"problem": 1, "disposition": disposition, "field": field, "url": url,
            "quote": quote, "changes": changes or {}, "explanation": explanation}


# ============================================================ failures -> the right row

def test_a_truncated_gate_name_maps_to_its_row():
    rows = [row(CONFERENCE="SecureWorld Government & Critical Infrastructure 2026"),
            row(CONFERENCE="SecureWorld East 2026")]
    text = "SecureWorld Government & Critical Infras: paraphrase, date IS on page"
    assert dl.match_row(text, rows)["CONFERENCE"].startswith("SecureWorld Government")


def test_an_ambiguous_prefix_maps_to_nobody():
    rows = [row(CONFERENCE="OWASP Global AppSec EU 2026 Vienna Speaking Track"),
            row(CONFERENCE="OWASP Global AppSec EU 2026 Vienna Speaking Track B")]
    assert dl.match_row("OWASP Global AppSec EU 2026 Vienna Speaking Tr: dup", rows) is None


def test_findings_classify_and_order_blocking_first():
    rows = [row(CONFERENCE="Alpha Summit 2026"), row(CONFERENCE="Zulu Expo 2026")]
    payload = {"x.csv": [
        {"check": "3", "name": "quote", "passed": False,
         "failures": ["Zulu Expo 2026: quote and date both absent - \"...\""]},
        {"check": "6b", "name": "order", "passed": False,
         "failures": ["no such row: deadline after start"]},
    ]}
    withdrawn = [mr.Repair("D", "Alpha Summit 2026", "Cybersecurity", "SUBMISSION URL", DEAD, "", "")]
    f, unmatched = dl.build_findings(rows, payload, [], withdrawn, "x.csv", "Cybersecurity", TODAY)
    assert [i["conference"] for i in f["rows"]] == ["Zulu Expo 2026", "Alpha Summit 2026"]
    assert f["rows"][0]["problems"][0]["kind"] == "deadline_evidence"
    assert f["rows"][1]["blocking"] is False and f["rows"][1]["problems"][0]["kind"] == "link"
    assert unmatched and "6b" in unmatched[0]


# ============================================================ answers -> verified or refused

def test_round5_live_form_replaces_the_dead_submission_link():
    r = row()
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans("replace", "SUBMISSION URL", FORM)),
                           TODAY, fetch({FORM: (200, "form")}), browser(set()))
    assert r["SUBMISSION URL"] == FORM and not res.for_person


def test_a_replacement_that_is_dead_is_refused():
    r = row()
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans("replace", "SUBMISSION URL", FORM)),
                           TODAY, fetch({FORM: (404, "")}), browser({FORM}))
    assert r["SUBMISSION URL"] == DEAD and "rejected" in res.for_person[0].what


def test_a_social_link_is_refused_even_if_it_loads():
    r = row()
    url = "https://www.linkedin.com/events/secureworld-east"
    dl.apply_answers([r], answers(r["CONFERENCE"], ans("replace", "SUBMISSION URL", url)),
                     TODAY, fetch({url: (200, "x")}), browser(set()))
    assert r["SUBMISSION URL"] == DEAD


def test_evidence_with_a_reformatted_quote_is_accepted_with_OUR_extraction():
    """The SecureWorld case: right page, upstream's quote reformatted the date."""
    r = row()
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans(
        "replace", "DEADLINE_EVIDENCE_URL", EVENTS, quote="October 4, 2026")),
        TODAY, fetch({EVENTS: (200, SECUREWORLD)}), browser(set()))
    assert r["DEADLINE_EVIDENCE_URL"] == EVENTS
    assert r["DEADLINE_QUOTE"] == "East 2026 2026-10-04"
    assert r["IS_PROJECTED"] == "false" and r["GROUNDING_CONFIDENCE"] == "Verified (2026)"
    assert r["SUBMISSION DEADLINE"] == "2026-10-04"
    assert any("extracted by us" in x.why for x in res.applied)


def test_evidence_that_does_not_state_the_deadline_is_refused():
    r = row(**{"SUBMISSION DEADLINE": "2026-10-05"})
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans(
        "replace", "DEADLINE_EVIDENCE_URL", EVENTS, quote="2026-10-04")),
        TODAY, fetch({EVENTS: (200, SECUREWORLD)}), browser(set()))
    assert r["DEADLINE_EVIDENCE_URL"] == "" and r["IS_PROJECTED"] == "true"
    assert "does not state" in res.for_person[0].detail


def test_a_homepage_cannot_be_evidence():
    r = row()
    home = "https://www.secureworld.io/"
    dl.apply_answers([r], answers(r["CONFERENCE"], ans(
        "replace", "DEADLINE_EVIDENCE_URL", home, quote="2026-10-04")),
        TODAY, fetch({home: (200, SECUREWORLD)}), browser(set()))
    assert r["DEADLINE_EVIDENCE_URL"] == ""


def test_propose_change_is_never_applied_H2_MEET_dates():
    r = row(CONFERENCE="H2 MEET 2026", **{"CONFERENCE DATES": "September 23 - September 25, 2026"})
    page = "\ud604\uc7a5 \ubc1c\ud45c 11\uc6d4 4\uc77c(\uc218) ~ 6\uc77c(\uae08)"
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans(
        "propose_change", url="https://www.h2meet.com/html/ko/speaker.php",
        quote="11\uc6d4 4\uc77c(\uc218) ~ 6\uc77c(\uae08)",
        changes={"CONFERENCE DATES": "November 4 - November 6, 2026", "START DATE": "2026-11-04"})),
        TODAY, fetch({"https://www.h2meet.com/html/ko/speaker.php": (200, page)}), browser(set()))
    assert r["CONFERENCE DATES"] == "September 23 - September 25, 2026"
    assert not res.applied
    assert "approve" in res.for_person[0].what
    assert res.for_person[0].detail.startswith("evidence checks out")


def test_none_public_withdraws_evidence_but_never_the_deadline():
    r = row(IS_PROJECTED="false", GROUNDING_CONFIDENCE="Verified (2026)",
            DEADLINE_EVIDENCE_URL=EVENTS, DEADLINE_QUOTE="x",
            **{"STATUS DETAILS": "Deadline October 4, 2026."})
    dl.apply_answers([r], answers(r["CONFERENCE"], ans("none_public", "DEADLINE_EVIDENCE_URL")),
                     TODAY, fetch({}), browser(set()))
    assert r["DEADLINE_EVIDENCE_URL"] == "" and r["DEADLINE_QUOTE"] == ""
    assert r["SUBMISSION DEADLINE"] == "2026-10-04" and r["IS_PROJECTED"] == "true"
    assert r["NOTES"] == "theirs"


def test_none_public_that_would_break_check_4_goes_to_a_person():
    r = row(IS_PROJECTED="false", DEADLINE_EVIDENCE_URL=EVENTS,
            **{"STATUS DETAILS": "The call is now open via an active form."})
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans("none_public", "DEADLINE_EVIDENCE_URL")),
                           TODAY, fetch({}), browser(set()))
    assert r["DEADLINE_EVIDENCE_URL"] == EVENTS
    assert "check 4" in res.for_person[0].what


def test_an_answer_for_a_row_not_in_the_delivery_is_reported():
    res = dl.apply_answers([row()], answers("Some Other Event", ans("replace", "SUBMISSION URL", FORM)),
                           TODAY, fetch({FORM: (200, "")}), browser(set()))
    assert res.for_person and "not in the delivery" in res.for_person[0].what


def test_rows_asking_only_other_questions_are_spent_last():
    """Pilot 2026-09-13: with a request cap, Denver's categories question - which can only reach a
    person's list - must not take a request ahead of a dead link the loop can actually fix."""
    rows = [row(CONFERENCE="A Denver 2026"), row(CONFERENCE="B East 2026")]
    declined = [mr.Declined("C", "A Denver 2026", "CATEGORIES", "serialised list")]
    withdrawn = [mr.Repair("D", "B East 2026", "Cybersecurity", "SUBMISSION URL", DEAD, "", "")]
    f, _ = dl.build_findings(rows, {}, declined, withdrawn, "x.csv", "Cybersecurity", TODAY)
    assert [i["conference"] for i in f["rows"]] == ["B East 2026", "A Denver 2026"]


def test_a_403_replacement_that_a_browser_shows_as_not_found_is_refused():
    """Pilot 2026-09-13: upstream answered events.secureworld.io/speaker-submission-form/, which a
    plain fetch saw as HTTP 403 and a real browser saw as "Page not found - SecureWorld"."""
    r = row()
    guess = "https://events.secureworld.io/speaker-submission-form/"
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans("replace", "SUBMISSION URL", guess)),
                           TODAY, fetch({guess: (403, "")}), browser({guess}))
    assert r["SUBMISSION URL"] == DEAD
    assert "not-found page" in res.for_person[0].detail


def test_a_403_that_a_browser_loads_is_still_accepted():
    r = row()
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans("replace", "SUBMISSION URL", FORM)),
                           TODAY, fetch({FORM: (403, "")}), browser(set()))
    assert r["SUBMISSION URL"] == FORM and not res.for_person


def test_a_proposal_whose_evidence_fails_says_so_first():
    """Pilot 2026-09-13, SecureWorld East: proposed page a browser 404, quote not on it, and it
    tried to change STATUS and five other fields for a question about one link."""
    r = row()
    bad = "https://events.secureworld.io/become-a-speaker/"
    res = dl.apply_answers([r], answers(r["CONFERENCE"], ans(
        "propose_change", url=bad, quote="East. October 4, 2026.",
        changes={"SUBMISSION URL": bad, "STATUS": "Open"})),
        TODAY, fetch({bad: (403, "")}), browser({bad}))
    assert not res.applied and r["STATUS"] == "Open" and r["SUBMISSION URL"] == DEAD
    d = res.for_person[0].detail
    assert d.startswith("EVIDENCE FAILS") and "not-found" in d and "quote is not on the page" in d


# ============================================================ link questions answered by crawl

def _findings(*items):
    return {"delivery": "x.csv", "market": "Cybersecurity", "today": "2026-09-13", "rows": list(items)}


def test_crawl_answers_link_questions_and_leaves_research_questions_alone():
    """The loop's default since 2026-09-13: links come from crawling the site, not from Gemini."""
    item = {"conference": "SecureWorld Government & Critical Infrastructure 2026",
            "row": {"CONFERENCE URL": "https://www.secureworld.io/", "MAIN_INFO_URL": ""},
            "problems": [
                {"kind": "link", "field": "SUBMISSION URL", "detail": "", "dead_url": DEAD},
                {"kind": "link", "field": "CFP_SUBMISSION_URL", "detail": "", "dead_url": DEAD},
                {"kind": "deadline_evidence", "field": "DEADLINE_EVIDENCE_URL", "detail": "",
                 "dead_url": ""}]}
    seen = []

    def hunt(jobs):
        seen.extend(jobs)
        return [{"PROPOSED URL": FORM, "VERDICT": "CONFIDENT", "WHY": "path states how to submit",
                 "START URL": "https://www.secureworld.io/", "FOUND VIA": "Submit a talk"}]

    out = dl.crawl_answers(_findings(item), hunt)
    assert len(seen) == 1 and seen[0]["submission_url"] == DEAD      # one crawl for one dead url
    answers = out["rows"][0]["answers"]
    assert [(x["field"], x["url"], x["disposition"]) for x in answers] == [
        ("SUBMISSION URL", FORM, "replace"), ("CFP_SUBMISSION_URL", FORM, "replace")]
    assert any("problem 3" in n and "needs research" in n for n in out["not_asked"])


def test_crawl_review_and_nothing_found_go_to_a_person_not_into_the_row():
    item = {"conference": "SecureWorld East 2026", "row": {"CONFERENCE URL": "https://x.test/"},
            "problems": [{"kind": "link", "field": "SUBMISSION URL", "detail": "", "dead_url": DEAD}]}
    review = dl.crawl_answers(_findings(item), lambda jobs: [
        {"PROPOSED URL": "https://x.test/speakers-info", "VERDICT": "REVIEW", "WHY": "plausible"}])
    assert not review["rows"][0]["answers"] and "needs review" in review["rows"][0]["issues"][0]
    nothing = dl.crawl_answers(_findings(item), lambda jobs: [
        {"PROPOSED URL": "", "VERDICT": "", "OUTCOME": "No live page found",
         "CFP STATE": "Call closed"}])
    assert not nothing["rows"][0]["answers"] and "Call closed" in nothing["rows"][0]["issues"][0]


def test_withdrawn_links_carry_their_dead_url_into_the_findings():
    rows = [row(CONFERENCE="B East 2026", **{"SUBMISSION URL": ""})]
    withdrawn = [mr.Repair("D", "B East 2026", "Cybersecurity", "SUBMISSION URL", DEAD, "", "")]
    f, _ = dl.build_findings(rows, {}, [], withdrawn, "x.csv", "Cybersecurity", TODAY)
    assert f["rows"][0]["problems"][0]["dead_url"] == DEAD
