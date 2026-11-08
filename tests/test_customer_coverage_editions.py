"""ACT-51, found 2026-11-08: a customer row linked to LAST year's edition counted as "in the research queue" although nobody researched
the edition the customer tracks (Black Hat USA 2027 linked to 2026-black-hat-usa-las-vegas; 5 such rows, 29 linked rows disagreeing).
The link covers the customer's row only when the linked event is the same edition (within the 30-day tolerance); otherwise the
customer's own edition must have an input row, else the row is NOT in the queue and the auto-add gate HOLDS it for a person,
naming the edition. A place-only disagreement (Dubai against "Middle East") keeps the link. FIXTURES ONLY (tmp_path)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from scripts import customer_auto_add as ca          # noqa: E402
from scripts import customer_coverage as cc          # noqa: E402
from test_customer_coverage import make_world, TODAY  # noqa: E402

BH_2026 = {"CONFERENCE": "Black Hat USA 2026", "CONFERENCE URL": "https://www.blackhat.com/us-26/", "START DATE": "8/1/2026",
           "EVENT_ID_CANON": "2026-black-hat-usa-las-vegas"}
BH_2027 = {"CONFERENCE": "Black Hat USA 2027", "CONFERENCE URL": "https://www.blackhat.com/us-27/", "START DATE": "7/31/2027"}
BH_FACT = {"event_id": "2026-black-hat-usa-las-vegas", "name": "Black Hat USA 2026", "url": "https://www.blackhat.com/us-26/",
           "city": "Las Vegas", "start_date": "2026-08-01"}
CUST_2027 = {"name": "Black Hat USA", "event_id": "2026-black-hat-usa-las-vegas", "url": "https://www.blackhat.com/us-27/",
             "start": "07/31/2027", "loc": "Mandalay Bay Convention Center, Las Vegas, NV"}


def run(tmp_path, client_rows, cyb_inputs, facts):
    db, md, led = make_world(tmp_path, client_rows, cyb_inputs, facts=facts)
    res, degraded, why = cc.run(db, md, led, TODAY)
    assert res is not None, why
    return res


def test_a_link_to_last_years_edition_does_not_put_the_customers_edition_in_the_queue(tmp_path):
    res = run(tmp_path, [CUST_2027], [BH_2026], [BH_FACT])
    assert [x["name"] for x in res["not_in_queue"]] == ["Black Hat USA"], res
    why = res["not_in_queue"][0]["why"]
    assert "another edition" in why and "2026-black-hat-usa-las-vegas" in why and "2027-07-31" in why
    assert len(res["disagree"]) == 1, "the disagreement is still reported"
    assert cc.summary_lines(res)[0].startswith("COVERAGE: 0 of 1 customer rows ahead of 2026-10-06 are in the research queue; 1 are NOT")


def test_the_customers_own_edition_on_the_list_puts_the_row_in_the_queue_despite_the_old_link(tmp_path):
    res = run(tmp_path, [CUST_2027], [BH_2026, BH_2027], [BH_FACT])
    assert not res["not_in_queue"], res["not_in_queue"]
    assert len(res["in_queue"]) == 1 and res["in_queue"][0]["input_row"] == "Black Hat USA 2027"
    assert "another edition" in res["in_queue"][0]["why"] and "URL and date" in res["in_queue"][0]["why"]


def test_a_link_to_the_same_edition_still_counts_by_event_id(tmp_path):
    # the same edition, a day apart on the two sides, still ahead of the fixture's today (2026-10-06)
    cust = {"name": "Winter Con", "event_id": "2026-winter-con-oslo", "url": "https://wintercon.example/2026", "start": "12/02/2026", "loc": "Oslo, Norway"}
    fact = {"event_id": "2026-winter-con-oslo", "name": "Winter Con 2026", "url": "https://wintercon.example/2026", "city": "Oslo", "start_date": "2026-12-01"}
    inputs = [{"CONFERENCE": "Winter Con 2026", "CONFERENCE URL": "https://wintercon.example/2026", "START DATE": "12/1/2026", "EVENT_ID_CANON": "2026-winter-con-oslo"}]
    res = run(tmp_path, [cust], inputs, [fact])
    assert len(res["in_queue"]) == 1 and res["in_queue"][0]["why"] == "by event id" and not res["disagree"]


def test_a_place_only_disagreement_keeps_the_link(tmp_path):
    cust = {"name": "ESF MENA", "event_id": "2026-esf-mena-dubai", "url": "https://esf.example/", "start": "12/16/2026", "loc": "Middle East"}
    fact = {"event_id": "2026-esf-mena-dubai", "name": "ESF MENA 2026", "url": "https://esf.example/", "city": "Dubai", "start_date": "2026-12-16"}
    inputs = [{"CONFERENCE": "ESF MENA 2026", "CONFERENCE URL": "https://esf.example/", "START DATE": "12/16/2026", "EVENT_ID_CANON": "2026-esf-mena-dubai"}]
    res = run(tmp_path, [cust], inputs, [fact])
    assert len(res["in_queue"]) == 1 and res["in_queue"][0]["why"] == "by event id"
    assert len(res["disagree"]) == 1 and res["disagree"][0]["why"].startswith("place:")


def test_a_row_without_a_linked_fact_is_judged_as_before(tmp_path):
    res = run(tmp_path, [CUST_2027], [BH_2026], [])
    assert len(res["in_queue"]) == 1 and res["in_queue"][0]["why"] == "by event id", "no fact to compare: the link stands, as it always did"


def test_the_auto_add_gate_holds_the_row_and_names_the_edition(tmp_path):
    db, md, led = make_world(tmp_path, [CUST_2027], [BH_2026], facts=[BH_FACT])
    out = tmp_path / "out"
    lines, _ = ca.run(TODAY, db, md, led, out, 10, False)
    assert "0 to add, 1 held for a person" in lines[0], lines
    assert lines[1].startswith("AUTOADD HELD: Black Hat USA")
    md_text = (out / "auto_add.md").read_text(encoding="utf-8")
    assert "another edition" in md_text and "2026-black-hat-usa-las-vegas" in md_text
    assert "proposed_additions.csv" and (out / "proposed_additions.csv").read_text(encoding="utf-8-sig").count("\n") <= 1, "nothing proposed for adding"
