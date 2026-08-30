"""A gate that did not run every check must not print ACCEPTED.

THE INCIDENT. On 2026-08-29 the v1.5 delivery was declared accepted and handed to upstream, who
began treating it as their production master. Every gate run had used `--no-network`, which
skips criteria 2 and 3 - the only two that fetch a cited page - and the gate printed
`RESULT: ACCEPTED` anyway, because a skipped check was excluded from the verdict.

A full networked run then failed check 3 on 183 rows.

Nothing in that output was false about any individual check. The SKIP lines were right there.
What was wrong was the single word everyone quotes, and no amount of reading the detail
protected against it - we read the detail every time and still repeated the mistake for a day.

So the verdict itself has to carry the doubt.
"""
import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("_ad", ROOT / "scripts" / "accept_delivery.py")
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)

HDR = ["EVENT_ID", "CONFERENCE", "CONFERENCE URL", "LOCATION", "CONFERENCE DATES",
       "LATEST UPDATE", "SUBMISSION DEADLINE", "SUBMISSION DATE VERIFIED", "PRIORITY",
       "STATUS", "STATUS DETAILS", "CFP MODEL TYPE", "SUBMISSION URL", "COORDINATOR EMAIL",
       "OVERVIEW", "CATEGORIES", "NOTES", "TRACK", "GROUNDING_CONFIDENCE", "EDITION",
       "START DATE", "Market", "CITY", "STATE_PROVINCE", "COUNTRY", "MAIN_INFO_URL",
       "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL", "VENUE_EVIDENCE_URL", "DEADLINE_QUOTE",
       "IS_PROJECTED", "SOURCE_AS_OF", "GATED_STATUS", "ISSUES", "OPPORTUNITY_TYPE", "FORMAT",
       "LIFECYCLE_EVIDENCE_URL", "LIFECYCLE_QUOTE", "ORGANIZER", "SPONSOR_REQUIRED",
       "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"]


def _clean_csv(tmp_path):
    """A file with nothing wrong in it, so only the skipping can change the verdict."""
    p = tmp_path / "d.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HDR)
        r = {c: "" for c in HDR}
        r.update({"EVENT_ID": "2027-clean-city-speaking", "CONFERENCE": "Clean Conf",
                  "Market": "Utility", "OPPORTUNITY_TYPE": "Speaking", "IS_PROJECTED": "true",
                  "GROUNDING_CONFIDENCE": "Projected (2027)", "SPONSOR_REQUIRED": "Unknown",
                  "SOURCE_AS_OF": "2026-08-01", "CITY": "Denver", "EDITION": "2027"})
        w.writerow([r[c] for c in HDR])
    return str(p)


def _run(path, network):
    g = ad.Gate(path, network=network)
    g.run(date(2026, 9, 1))
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = g.report()
    return ok, buf.getvalue()


def test_a_skipped_check_cannot_produce_accepted(tmp_path):
    """The exact 2026-08-29 failure: --no-network skips 2 and 3 and the file otherwise passes."""
    ok, out = _run(_clean_csv(tmp_path), network=False)
    assert "ACCEPTED" not in out, (
        "a run that skipped checks printed ACCEPTED - this is the 2026-08-29 defect:\n" + out)
    assert "INCOMPLETE" in out, "say plainly that it was not fully run"
    assert ok is False, "a partial run must not gate a pipeline step as success"


def test_the_skipped_checks_are_named(tmp_path):
    """'Incomplete' without saying WHICH invites someone to assume it was something minor."""
    _ok, out = _run(_clean_csv(tmp_path), network=False)
    assert "NOT RUN" in out
    assert "2" in out and "3" in out, "name the criteria that did not run"
    assert "--no-network" in out, "say how to get a real verdict"


def test_a_full_run_on_a_clean_file_still_accepts(tmp_path, monkeypatch):
    """The guard must not make ACCEPTED unreachable - a gate that never accepts is ignored."""
    import src.cfp_monitor.verify as verify
    monkeypatch.setattr(verify, "link_status", lambda u: (200, ""))
    monkeypatch.setattr(verify, "fetch_text", lambda u, **k: ("", ""))
    ok, out = _run(_clean_csv(tmp_path), network=True)
    assert "INCOMPLETE" not in out, "nothing was skipped, so nothing should be reported as unrun"
    assert ok is True and "ACCEPTED" in out


def test_a_real_failure_still_says_rejected(tmp_path):
    """REJECTED must outrank INCOMPLETE - a failure is worse news than an unrun check."""
    p = tmp_path / "bad.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(HDR[:38])                     # wrong width - fails check 1
        w.writerow(["x"] * 38)
    _ok, out = _run(str(p), network=False)
    assert "REJECTED" in out and "INCOMPLETE" not in out
