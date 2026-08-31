"""N3: the customer sees what we did for them, and only their own rows.

We reconcile against the customer's sheet every week - what they asked us to verify, what we
found, what moved. All of it landed on our side and none of it reached them. The loop was closed
for us and invisible to them.

The two rules that matter here are isolation and honesty. A client must never see another
client's rows, and "we could not confirm this" is a real answer that belongs in the list -
silence reads as having been ignored, which is worse than a plain admission (2.6).
"""
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import client_view          # noqa: E402

TODAY = date(2026, 8, 31)


def _db():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        create table clients (client_key text, name text, industry text);
        create table client_conferences (
            client_key text, their_name text, event_id text, their_deadline text,
            match_confidence real, submission_date_verified text,
            withdrawn_by_customer integer default 0);
        create table grounding_facts (
            event_id text, deadline text, deadline_quote text, deadline_evidence_url text,
            verify_state text, status text, source_as_of text);
        insert into clients values ('arnica','Arnica','Cybersecurity'),
                                  ('other','Other Co','Cybersecurity');
    """)
    return con


def _ask(con, client, name, eid="", deadline="", quote="", url="", conf=None, theirs=""):
    con.execute("insert into client_conferences values (?,?,?,?,?,'Needs Verification',0)",
                (client, name, eid, theirs, conf))
    if eid:
        con.execute("insert into grounding_facts values (?,?,?,?,'verified','Open','2026-08-31')",
                    (eid, deadline, quote, url))
    con.commit()


def test_a_confirmed_deadline_says_where_we_read_it():
    con = _db()
    _ask(con, "arnica", "DEF CON 34", "e1", "2026-05-01",
         "The deadline for submissions is May 1, 2026 at Midnight UTC.",
         "https://defcon.org/html/defcon-34/dc-34-cfp.html")
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["state"] == "confirmed"
    assert "2026-05-01" in a["answer"] and "read it there" in a["answer"]
    assert a["quote"].startswith("The deadline")
    assert a["url"].startswith("https://defcon.org")


def test_no_deadline_announced_is_a_real_answer_not_a_failure():
    """It is a fact about the conference. Phrasing it as our shortcoming would be dishonest and
    would make the customer chase us instead of the organiser."""
    con = _db()
    _ask(con, "arnica", "CrowdStrike Fal.Con", "e1")
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["state"] == "no date announced"
    assert "not a gap in our checking" in a["answer"]


def test_a_date_we_hold_but_could_not_confirm_says_unchecked_not_doubtful():
    con = _db()
    _ask(con, "arnica", "Some Conf", "e1", "2026-11-01")
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["state"] == "held, not confirmed"
    assert "unchecked rather than doubtful" in a["answer"]


def test_an_unmatched_row_asks_the_customer_rather_than_going_quiet():
    con = _db()
    _ask(con, "arnica", "Wild West Hackin Fest", conf=90.0)
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["state"] == "asking you"
    assert "will not guess" in a["answer"]


def test_a_conference_we_do_not_track_says_so_plainly():
    con = _db()
    _ask(con, "arnica", "KubeCon", conf=0.0)
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["state"] == "not tracked"
    assert "Tell us to add it" in a["answer"]


def test_a_client_never_sees_another_clients_rows():
    """The isolation rule. Two clients in one industry must never see each other exist."""
    con = _db()
    _ask(con, "arnica", "Arnica Only", "e1", "2026-11-01", "q", "https://a.example/")
    _ask(con, "other", "Other Only", "e2", "2026-12-01", "q", "https://b.example/")
    mine = [a["name"] for a in client_view.answered(con, "arnica", TODAY)]
    assert mine == ["Arnica Only"]
    theirs = [a["name"] for a in client_view.answered(con, "other", TODAY)]
    assert theirs == ["Other Only"]


def test_a_withdrawn_row_is_not_reported_back_to_them():
    con = _db()
    _ask(con, "arnica", "Gone", "e1", "2026-11-01")
    con.execute("update client_conferences set withdrawn_by_customer = 1")
    con.commit()
    assert client_view.answered(con, "arnica", TODAY) == []


def test_their_own_deadline_is_carried_so_a_difference_can_be_explained():
    """When a conference runs tiered rounds both sides can be right, and the page says so
    rather than implying one of us is wrong."""
    con = _db()
    _ask(con, "arnica", "Climate Change", "e1", "2026-12-20", "q", "https://x.example/",
         theirs="10/19/2026")
    a = client_view.answered(con, "arnica", TODAY)[0]
    assert a["their_deadline"] == "10/19/2026" and a["deadline"] == "2026-12-20"


def test_changes_are_scoped_to_the_client_too():
    con = _db()
    _ask(con, "arnica", "Mine", "e1", "2026-11-01", "q", "https://a.example/")
    _ask(con, "other", "Theirs", "e2", "2026-12-01", "q", "https://b.example/")
    got = [c["name"] for c in client_view.changed_for_client(con, "arnica", "2026-08-01")]
    assert got == ["Mine"]


def test_summary_counts_are_derived_from_the_list():
    con = _db()
    _ask(con, "arnica", "A", "e1", "2026-11-01", "q", "https://a.example/")
    _ask(con, "arnica", "B", "e2")
    _ask(con, "arnica", "C", "e3")
    s = client_view.summary(client_view.answered(con, "arnica", TODAY))
    assert s["confirmed"] == 1 and s["no date announced"] == 2


def test_the_shared_page_is_untouched_without_a_client():
    """A feature that quietly changes existing output is how a page nobody asked to change
    ends up in front of a customer."""
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "if not ctx:\n        return ''" in src


def test_scoping_to_zero_rows_is_an_error_not_an_empty_page():
    """An empty page looks exactly like a client who tracks nothing. It is a join failure."""
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "left NO rows of" in src
    # The message is split across two source lines, so match on the collapsed text rather than
    # a phrase that only exists once the strings are concatenated.
    assert "join" in src and "not a client who tracks nothing" in src
    assert "raise SystemExit(" in src.split("left NO rows of")[0][-400:]


def test_the_common_answer_is_grouped_not_repeated():
    """Twenty identical sentences bury the four rows that differ - the same failure as listing
    every untouched row in the weekly digest."""
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "No deadline announced yet" in src
    assert "individual = [r for r in answers if r['state'] != 'no date announced']" in src
