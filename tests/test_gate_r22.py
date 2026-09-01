"""R22 must be a check of its own, offline, over every evidence column.

WHY THIS TEST EXISTS
R22 was agreed in contract v1.6 on 2026-08-31 and the acceptance gate never enforced it. The
consequence sat in a shipped delivery: ACT Expo 2027 cited `https://www.facebook.com/ACTExpo/`
for a submission deadline, labelled `Verified (2027)`, and every gate run passed it. It only
surfaced on 2026-09-01 because that row happened to fail the QUOTE check for an unrelated
reason.

That near-miss is the whole design argument. Had the quote been present on the Facebook page,
check 3 would have passed and nothing would ever have objected.
"""
import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

COLS = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL",
        "DEADLINE_QUOTE", "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE", "SPONSOR_URL",
        "SPONSOR_REQUIRED", "IS_PROJECTED", "GROUNDING_CONFIDENCE", "STATUS", "STATUS DETAILS"]


def _gate(tmp_path, rows):
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    g = ad.Gate(str(p), network=False)
    with open(p, encoding="utf-8-sig", newline="") as fh:
        g.rows = list(csv.DictReader(fh))
    g.check_schema_rules()
    return {num: (ok, fails) for num, _name, ok, fails in g.results}


def _r22(tmp_path, rows):
    res = _gate(tmp_path, rows)
    assert "R22" in res, "the gate must report an R22 result at all"
    return res["R22"]


def test_a_facebook_citation_fails(tmp_path):
    """The row that was actually shipped."""
    ok, fails = _r22(tmp_path, [{
        "CONFERENCE": "ACT Expo 2027",
        "SUBMISSION DEADLINE": "2026-09-10",
        "DEADLINE_EVIDENCE_URL": "https://www.facebook.com/ACTExpo/",
        "DEADLINE_QUOTE": "Call for Speakers closes September 10",
        "IS_PROJECTED": "false", "GROUNDING_CONFIDENCE": "Verified (2027)"}])
    assert not ok and len(fails) == 1
    assert "facebook.com" in fails[0] and "ACT Expo" in fails[0]


def test_it_fails_even_when_the_quote_would_be_found(tmp_path):
    """The design point. R22 asks WHO is speaking, before anything asks what the page says -
    so a well-formed quote on an inadmissible host must still fail. Folded into the quote
    check, this row would have passed."""
    ok, _ = _r22(tmp_path, [{
        "CONFERENCE": "Any Conf",
        "DEADLINE_EVIDENCE_URL": "https://twitter.com/anyconf/status/123",
        "DEADLINE_QUOTE": "Submissions close 1 October 2026"}])
    assert not ok


def test_a_lifecycle_citation_is_held_to_the_same_standard(tmp_path):
    """A discontinuation cited to a social post is the same defect as a deadline cited to one.
    Until 2026-09-01 the rule was only ever asked about DEADLINE_EVIDENCE_URL."""
    ok, fails = _r22(tmp_path, [{
        "CONFERENCE": "Gone Conf 2027", "STATUS": "Closed",
        "LIFECYCLE_EVIDENCE_URL": "https://www.linkedin.com/posts/someone-activity-123",
        "LIFECYCLE_QUOTE": "We are winding the event down"}])
    assert not ok and "LIFECYCLE_EVIDENCE_URL" in fails[0]


def test_a_sponsor_url_is_held_to_the_same_standard(tmp_path):
    ok, fails = _r22(tmp_path, [{
        "CONFERENCE": "Pay Conf 2027", "SPONSOR_REQUIRED": "Yes",
        "SPONSOR_URL": "https://bit.ly/3xyzabc"}])
    assert not ok and "SPONSOR_URL" in fails[0]


def test_an_organiser_url_passes(tmp_path):
    ok, fails = _r22(tmp_path, [{
        "CONFERENCE": "Good Conf 2027",
        "DEADLINE_EVIDENCE_URL": "https://goodconf.example/call-for-papers",
        "LIFECYCLE_EVIDENCE_URL": "", "SPONSOR_URL": "https://goodconf.example/sponsor"}])
    assert ok and not fails


def test_blank_citations_are_not_a_violation(tmp_path):
    """2.1 - a row with no citation is unevidenced, not inadmissible. R2 and R16 police
    missing evidence; R22 polices bad evidence. Conflating them would fail every stub."""
    ok, _ = _r22(tmp_path, [{"CONFERENCE": "Stub Conf 2027", "IS_PROJECTED": "true"}])
    assert ok


def test_it_runs_without_network(tmp_path):
    """R22 needs no fetch, so --no-network must not skip it. Checks 2 and 3 are skipped there,
    which is exactly why R22 must not live inside them."""
    res = _gate(tmp_path, [{
        "CONFERENCE": "Any Conf",
        "DEADLINE_EVIDENCE_URL": "https://www.facebook.com/x/"}])
    ok, _ = res["R22"]
    assert not ok, "R22 must still fire with network=False"


def test_one_row_citing_two_bad_sources_reports_both(tmp_path):
    """A per-row short-circuit would hide the second one, and someone would fix the deadline,
    re-run, and be surprised."""
    ok, fails = _r22(tmp_path, [{
        "CONFERENCE": "Double Conf 2027",
        "DEADLINE_EVIDENCE_URL": "https://www.facebook.com/dc/",
        "SPONSOR_URL": "https://t.co/abc"}])
    assert not ok and len(fails) == 2
