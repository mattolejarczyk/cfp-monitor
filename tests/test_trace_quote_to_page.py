"""The trace tool must route every decision through the rules layer, not its own judgement.

This script DELETES a citation when it cannot find the quote, which makes it the most
destructive tool in the repo. Its predecessor proposed 18 withdrawals on 2026-08-29 of which 14
were wrong - passed-deadline rows whose CFP page had simply come down. The safety is not in this
script being careful; it is in `rules.may_withdraw_citation` refusing, and these tests check the
wiring rather than the intention.
"""
import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_tq", ROOT / "scripts" / "trace_quote_to_page.py")
tq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tq)

TODAY = date(2026, 8, 29)
COLS = ["EVENT_ID", "CONFERENCE", "SUBMISSION DEADLINE", "DEADLINE_EVIDENCE_URL",
        "DEADLINE_QUOTE", "IS_PROJECTED", "GROUNDING_CONFIDENCE", "SOURCE_AS_OF"]


def _df(rows):
    return pd.DataFrame(rows, columns=COLS).astype(str)


def _row(eid="e1", name="Conf", deadline="2026-12-01", url="https://x.example/cfp",
         quote="Abstracts due 1 December 2026"):
    return [eid, name, deadline, url, quote, "false", "Verified (2026)", "2026-08-01"]


def test_only_rows_with_both_a_citation_and_a_quote_are_considered():
    df = _df([_row(), _row("e2", "No Quote", quote=""), _row("e3", "No URL", url="")])
    sel = tq._wanted(df, None, "")
    assert list(sel) == [True, False, False]


def test_rows_csv_narrows_by_event_id(tmp_path):
    df = _df([_row("e1", "Alpha"), _row("e2", "Beta")])
    p = tmp_path / "subset.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "CONFERENCE"])
        w.writeheader()
        w.writerow({"EVENT_ID": "e2", "CONFERENCE": "Beta"})
    assert list(tq._wanted(df, str(p), "")) == [False, True]


def test_a_passed_deadline_is_never_withdrawn_by_this_tool():
    """The 14-row mistake. The refusal lives in rules, and this asserts the tool asks it."""
    from src.cfp_monitor import rules
    r = dict(zip(COLS, _row(deadline="2026-06-17")))
    may, why = rules.may_withdraw_citation(r, quote_found=False, pages_read=50, today=TODAY)
    assert may is False and "deadline passed" in why


def test_an_unreadable_site_is_never_withdrawn():
    from src.cfp_monitor import rules
    r = dict(zip(COLS, _row()))
    may, why = rules.may_withdraw_citation(r, quote_found=False, pages_read=0, today=TODAY)
    assert may is False and "no page could be read" in why


def test_a_withdrawal_carries_all_four_fields():
    """Three of four was the defect twice in one day."""
    from src.cfp_monitor import rules
    r = dict(zip(COLS, _row()))
    ch = rules.withdrawal_changes(r, fetched=True, today=TODAY)
    assert ch["DEADLINE_EVIDENCE_URL"] == "" and ch["DEADLINE_QUOTE"] == ""
    assert ch["IS_PROJECTED"] == "true"
    assert ch["GROUNDING_CONFIDENCE"] == "Projected (2026)"
    assert ch["SOURCE_AS_OF"] == "2026-08-29"
    assert "SUBMISSION DEADLINE" not in ch, "R1 never touches the deadline"


def test_it_uses_sitewalk_rather_than_its_own_crawler():
    """The reason this script could move into the repo at all."""
    src = (ROOT / "scripts" / "trace_quote_to_page.py").read_text(encoding="utf-8")
    assert "sitewalk.plan" in src and "sitewalk.rank_links" in src
    assert "urljoin" not in src, "URL joining belongs in sitewalk"


def test_no_partial_quote_matching():
    """An earlier version accepted a 35-character prefix, which can attach a citation to the
    wrong page - worse than none, because it looks verified."""
    src = (ROOT / "scripts" / "trace_quote_to_page.py").read_text(encoding="utf-8")
    assert "[:35]" not in src and "short_quote" not in src
