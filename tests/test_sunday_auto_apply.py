"""Sunday's unattended discovery merge (operator, 2026-09-28): strict proof, safety net, recap."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from apply_resolutions import deadline_in_quote          # noqa: E402
import weekly_discovery as wd                            # noqa: E402
from weekend_recap import discovery_section              # noqa: E402


def test_deadline_must_be_written_inside_the_quote():
    q = "Call for Papers submission deadline: December 4, 2026"
    assert deadline_in_quote(q, "2026-12-04")            # the format discovery writes
    assert deadline_in_quote(q, "December 4, 2026")
    # a quote naming a different date, or none, proves nothing about this deadline
    assert not deadline_in_quote(q, "2026-12-05")
    assert not deadline_in_quote("Submissions are now open", "2026-12-04")
    assert not deadline_in_quote(q, "")


def test_dashed_dates_count_but_ambiguous_ones_are_refused():
    assert deadline_in_quote("Opens 7-13-2026 (closes 10-15-2026)", "2026-10-15")
    # 12/4/2026 could be April 12 or December 4 - never guessed
    assert not deadline_in_quote("deadline: December 4, 2026", "12/4/2026")
    assert deadline_in_quote("deadline: January 26, 2027", "1/26/2027")   # unambiguous


def test_a_quote_announcing_an_extension_is_never_auto_applied():
    q = "Abstract Submissions Due: September 30, 2026 ------Extended to October 15, 2026"
    assert not deadline_in_quote(q, "2026-09-30")
    assert not deadline_in_quote(q, "2026-10-15")


def test_a_failed_merge_is_rolled_back_byte_for_byte(tmp_path):
    db = tmp_path / "cfp_monitor.db"
    db.write_bytes(b"ORIGINAL")
    # a merge that damages the database and then fails
    bad_merge = [sys.executable, "-c",
                 f"import sys; open(r'{db}', 'ab').write(b'-DAMAGED'); sys.exit(1)"]
    a = SimpleNamespace(db=str(db), protect_delivery=None)
    wd.auto_apply(a, bad_merge, tmp_path, "20260928", {})
    assert db.read_bytes() == b"ORIGINAL"
    res = json.loads((tmp_path / "weekly_discovery_result_20260928.json").read_text())
    assert res["status"] == "ROLLED BACK"
    assert list(tmp_path.glob("cfp_monitor.pre-discovery-*.db"))      # the backup is kept


def test_recap_lists_applied_findings_and_says_when_nothing_ran():
    lines, rows = discovery_section({
        "status": "APPLIED", "proposed": 3,
        "accepted": [{"conference": "Pittcon 2027", "old_deadline": "", "new_deadline": "8/15/2026",
                      "new_url": "https://pittcon.org/call"}],
        "rejected": [{"conference": "X", "why": "the deadline is not written in the quote"}],
        "kept": [{"conference": "Y", "why": "on a customer's approved page"}]})
    assert "1 applied" in lines[0] and "1 not proven" in lines[0]
    assert rows == [["Pittcon 2027", "-", "8/15/2026", "https://pittcon.org/call"]]
    lines, rows = discovery_section({"status": "ROLLED BACK", "why": "health check failed",
                                     "proposed": 2, "accepted": [{"conference": "Z"}]})
    assert rows == [] and any("restored" in x for x in lines)
    assert "did not run" in discovery_section(None)[0][0]
