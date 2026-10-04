"""scripts/shadow_finder.py: which rows it reads, how it relates its answer to ours, and that it is read-only."""
import re
from pathlib import Path

from scripts.shadow_finder import relation, report_md, select_events, summarize

T = "2026-10-04"


def row(**k):
    base = {"CONFERENCE": "E", "EVENT_ID": "id", "STATUS": "Open", "EDITION": "2027", "START DATE": "2027-05-01", "SUBMISSION DEADLINE": "2026-12-01",
            "MAIN_INFO_URL": "https://e.org/", "CONFERENCE URL": "", "CFP_SUBMISSION_URL": "", "DEADLINE_EVIDENCE_URL": "", "_market": "Cybersecurity"}
    base.update(k)
    return base


def test_only_live_rows_with_a_page_are_read_soonest_deadline_first():
    rows = [row(CONFERENCE="late", **{"SUBMISSION DEADLINE": "2027-01-10"}), row(CONFERENCE="soon", **{"SUBMISSION DEADLINE": "2026-10-20"}),
            row(CONFERENCE="closed", STATUS="Closed"), row(CONFERENCE="past", **{"START DATE": "2026-09-01"}), row(CONFERENCE="old", EDITION="2026", **{"START DATE": ""}) if False else row(CONFERENCE="oldyear", EDITION="2025"),
            row(CONFERENCE="nopage", MAIN_INFO_URL=""), row(CONFERENCE="blank", **{"SUBMISSION DEADLINE": ""})]
    out = select_events(rows, T, 10)
    assert [e["event"] for e in out] == ["soon", "late", "blank"]
    assert select_events(rows, T, 1)[0]["event"] == "soon" and out[0]["hosts"] == ["e.org"]


def test_relation_and_summary():
    assert relation("2026-11-16", "2026-11-16") == "agree" and relation("2026-11-16", "2026-11-23") == "differs"
    assert relation("", "2026-11-16") == "real-only" and relation("2026-11-16", "") == "ours-only" and relation("", "") == "none"
    s = summarize([{"relation": "agree"}, {"relation": "differs"}, {"relation": "differs"}])
    assert s["differs"] == 2 and s["agree"] == 1 and s["none"] == 0


def test_report_lists_the_disagreements_and_says_nothing_was_changed():
    recs = [{"event": "X", "market": "Cybersecurity", "ours": "2026-11-23", "grounded": "2026-11-23", "pick": "2026-11-16", "relation": "differs", "why": "main-page", "pick_url": "https://x/cfp", "quote": "Deadline Nov 16, 2026"}]
    md = report_md(recs, summarize(recs), {"stamp": "s", "selected": 1, "skipped": 0, "stopped": "", "minutes": 1.0, "usd": 0.004})
    assert "changes nothing" in md and "Differs" in md and "2026-11-16" in md


def test_the_shadow_script_never_writes_to_the_database_or_the_approved_files():
    src = Path("scripts/shadow_finder.py").read_text(encoding="utf-8")
    code = re.sub(r'""".*?"""', "", src, flags=re.S)
    assert not re.search(r"insert\s+(or\s+\w+\s+)?into|update\s+\w+\s+set|delete\s+from|executescript|\.final\.csv[\"']\s*,\s*[\"']w|promote_delivery|apply_pins", code, re.I)
    assert "sqlite3.connect" not in code
