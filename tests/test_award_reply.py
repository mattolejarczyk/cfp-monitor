"""ACT-67 follow-up 3: upstream's reply with award ids - scripts/customer_awards.py --reply-plan and --relabel, the reviewed file, and the import rules it needs. FIXTURES ONLY."""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from scripts import customer_awards as ca                      # noqa: E402
from scripts import stamp_given_ids as sgi                      # noqa: E402
import scripts.weekend_import as wi                             # noqa: E402
from test_customer_awards import world, read, write, unlabel_world, TODAY      # noqa: E402
import test_first_load_awards as tfa                            # noqa: E402

COLS = ["market", "award_name", "action", "event_id", "survivor", "note"]


def reply_world(tmp_path):
    inp = [{"CONFERENCE": "Cloud Awards Security", "SUBMISSION URL": "https://cloud.example/s", "Market": "Cybersecurity", "EVENT_ID_CANON": "2027-cloud-security-tbd-awards"},
           {"CONFERENCE": "Cloud Security Awards - SaaS family", "SUBMISSION URL": "https://cloud.example/saas", "Market": "Cybersecurity"},
           {"CONFERENCE": "Brand New Award", "SUBMISSION URL": "https://bn.example/enter?AwardID=7", "Market": "Cybersecurity"},
           {"CONFERENCE": "Held Computing Awards (site)", "SUBMISSION URL": "https://hc.example/a", "Market": "Cybersecurity"},
           {"CONFERENCE": "Sibling Award", "SUBMISSION URL": "https://sb.example/a", "Market": "Cybersecurity", "DUP_OF": "MARKET_SIBLING", "EVENT_ID_CANON": "2027-sibling-nan-awards"}]
    reply = [{"market": "Cybersecurity", "award_name": "Cloud Security Awards - SaaS family", "action": "RELABEL", "event_id": "", "survivor": "Cloud Awards Security", "note": ""},
             {"market": "Cybersecurity", "award_name": "Brand New Award", "action": "NEW", "event_id": "2026-brand-new-award-nan-awards", "survivor": "", "note": ""},
             {"market": "Cybersecurity", "award_name": "Held Computing Awards (site)", "action": "STAMP_EXISTING", "event_id": "2026-held-computing-tbd-awards", "survivor": "", "note": ""}]
    sheets, md, led = world(tmp_path, inputs=inp)
    rp = tmp_path / "reply.csv"
    write(rp, COLS, reply)
    return md, rp, reply


def test_reply_plan_sorts_each_row_and_writes_the_ids_files_with_our_url_and_the_exact_row_name(tmp_path):
    md, rp, _ = reply_world(tmp_path)
    assert ca.run_reply_plan(rp, md, tmp_path / "o", None)[0] == "AWARDS REPLY: 1 new ids to stamp, 1 existing ids to stamp, 1 to relabel, 0 already done, 0 problems"
    new = read(tmp_path / "o" / "ids_new.csv")
    assert new == [{"sheet": "Awards", "id": "2026-brand-new-award-nan-awards", "start": "", "url": "https://bn.example/enter?AwardID=7", "conference": "Brand New Award"}]
    assert read(tmp_path / "o" / "ids_existing.csv")[0]["id"] == "2026-held-computing-tbd-awards"
    _c, rows, _b, _x = ca.acr.read_input(md / "Awards_input.csv")
    pl = sgi.plan([new[0]], {"Awards": rows}, set(), {})
    assert [rows[k]["CONFERENCE"] for _, k, _ in pl["stamp"]] == ["Brand New Award"]


def test_reply_plan_refuses_a_collision_a_still_labelled_row_a_known_id_and_an_id_not_in_the_database(tmp_path):
    md, rp, reply = reply_world(tmp_path)
    inp = read(md / "Awards_input.csv")
    r = [dict(x) for x in reply]
    r[2]["event_id"] = "2027-cloud-security-tbd-awards"
    assert any("would collide" in p for p in ca.reply_plan(r, inp)["problems"]), "a second row with the survivor's id"
    inp[3]["DUP_OF"] = "Cloud Awards Security"
    r = [dict(reply[1], award_name="Cloud Security Awards - SaaS family", event_id="2026-x-nan-awards")]
    assert any("still labelled DUP_OF" in p for p in ca.reply_plan(r, inp)["problems"])
    inp[3]["DUP_OF"] = ""
    assert any("already held" in p for p in ca.reply_plan([dict(reply[1], event_id="2027-cloud-security-tbd-awards")], inp)["problems"]), "a NEW id an input row carries is not new"
    assert any("not in the database" in p for p in ca.reply_plan([reply[2]], inp, {"2026-other-tbd-awards"})["problems"])
    assert any("survivor" in p for p in ca.reply_plan([dict(reply[0], survivor="No Such Award")], inp)["problems"])


def test_relabel_sets_dup_of_on_exactly_the_same_award_rows_and_a_second_apply_changes_nothing(tmp_path):
    md, rp, _ = reply_world(tmp_path)
    old = read(md / "Awards_input.csv")
    assert ca.run_relabel(rp, md, tmp_path / "o", False)[0] == "AWARDS RELABEL: mode=dry-run; 1 to relabel; 0 already done; 0 not relabelled"
    assert read(md / "Awards_input.csv") == old
    assert ca.run_relabel(rp, md, tmp_path / "o", True)[0].startswith("AWARDS RELABEL: mode=applied; 1 relabelled")
    new = read(md / "Awards_input.csv")
    assert {(i, c) for i, (a, b) in enumerate(zip(old, new)) for c in a if a[c] != b[c]} == {(3, "DUP_OF")} and new[3]["DUP_OF"] == "Cloud Awards Security"
    assert new[6]["DUP_OF"] == "MARKET_SIBLING"
    assert list(md.glob("Awards_input.pre-relabel-*.bak.csv"))
    assert ca.run_relabel(rp, md, tmp_path / "o", True)[0].startswith("AWARDS RELABEL: mode=applied; 0 relabelled; 1 already done")
    assert read(md / "Awards_input.csv") == new


def test_relabel_is_the_inverse_of_unlabel(tmp_path):
    sheets, md, led = unlabel_world(tmp_path)
    old = read(md / "Awards_input.csv")
    ca.run_unlabel(TODAY, sheets, md, tmp_path / "o1", True)
    rp = tmp_path / "reply.csv"
    write(rp, COLS, [{"market": "Cybersecurity", "award_name": "Fortress Award (Business Intelligence Group)", "action": "RELABEL", "event_id": "", "survivor": "Fortress Award"}])
    ca.run_relabel(rp, md, tmp_path / "o2", True)
    new = read(md / "Awards_input.csv")
    assert new[3]["DUP_OF"] == "Fortress Award" and new[3]["CONFERENCE"] == old[3]["CONFERENCE"]
    assert {c: new[3][c] for c in new[3] if c != "EVENT_ID_CANON"} == {c: old[3][c] for c in old[3] if c != "EVENT_ID_CANON"}


def test_relabel_on_the_live_markets_folder_needs_the_switch(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["customer_awards.py", "--relabel", "--reply", "x.csv", "--apply", "--markets-dir", str(ca.MARKETS)])
    assert ca.main() == 0
    assert "AWARDS RELABEL: REFUSED" in capsys.readouterr().out


def test_the_committed_reply_file_is_ascii_has_the_agreed_shape_and_never_uses_a_new_id_for_a_same_ruling():
    p = ROOT / "docs" / "operations" / "award_ids_reply_20261012.csv"
    assert p.read_text(encoding="utf-8").isascii()
    rows = read(p)
    assert Counter(r["action"] for r in rows) == {"NEW": 30, "RELABEL": 7, "STAMP_EXISTING": 2, "STAMP_NONAWARD": 2}
    assert all(r["survivor"] and not r["event_id"] for r in rows if r["action"] == "RELABEL")
    assert all(r["event_id"] for r in rows if r["action"] != "RELABEL")
    ids = [r["event_id"] for r in rows if r["event_id"]]
    assert len(ids) == len(set(ids))


def test_a_researched_row_typed_as_a_non_award_is_never_first_loaded_as_an_award_and_is_named(tmp_path, monkeypatch):
    """import_awards leaves a row not typed 'Awards' out of the award tables, so a first load of it would be 'expected but absent' and undo the whole Friday load."""
    md, led, db = tfa.world(tmp_path)
    rows = list(csv.reader(open(md / "Awards_audited.csv", encoding="utf-8")))
    rows[1][tfa.COLS.index("OPPORTUNITY_TYPE")] = "Speaking"
    tfa.write(md / "Awards_audited.csv", rows[0], rows[1:])
    res = tfa.resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    assert [e["canonical"] for e in res["new_events"]] == [tfa.NEW2, tfa.NEW3]
    h = [x for x in res["new_events_held"] if x["conference"] == "Alpha Prize"]
    assert h and h[0]["kind"] == "not_award" and "not an award" in h[0]["reason"]


def test_a_carried_non_award_row_is_superseded_by_this_weeks_award_row_of_the_same_name(tmp_path, monkeypatch):
    md, led, db = tfa.world(tmp_path)
    prior = ["Market", "EVENT_ID", "CONFERENCE", "SUBMISSION URL", "STATUS DETAILS", "EDITION", "SUBMISSION DEADLINE", "STATUS", "OPPORTUNITY_TYPE"]
    tfa.write(md / "Awards_audited.final.csv", prior, [["Cybersecurity", "old-spk", "Alpha Prize", "", "", "2026", "", "", "Speaking"], ["Cybersecurity", "old-keep", "Kept Prize", "", "", "2026", "", "", "Speaking"]])
    res = tfa.resolve(tmp_path, monkeypatch, md, led, db, enabled=True)
    names = [(r["CONFERENCE"], r["OPPORTUNITY_TYPE"]) for r in csv.DictReader(open(res["candidate"], encoding="utf-8"))]
    assert names.count(("Alpha Prize", "Awards")) == 1 and ("Alpha Prize", "Speaking") not in names, "the customer sees the listing once"
    assert ("Kept Prize", "Speaking") in names, "a carried non-award nobody re-researched is untouched"
    assert any(d["action"] == "superseded" and d["conference"] == "Alpha Prize" for d in res["decisions"])
