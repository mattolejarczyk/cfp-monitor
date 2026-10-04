"""The row-by-row rule in scripts/weekend_import.py (agreed 2026-09-27).

Passing rows ship; a failing row is replaced by last week's accepted version of the same event,
matched through identity.to_canonical; a failing row with no usable prior is held back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.weekend_import import (apply_row_rule, invariant_failures,  # noqa: E402
                                    map_failures, rows_for_failure)


def row(name, eid, **kw):
    return {"CONFERENCE": name, "EVENT_ID": eid, **kw}


def test_good_rows_survive_untouched():
    rows = [row("Alpha Con 2026", "up-a"), row("Beta Summit 2026", "up-b")]
    decisions = []
    out, src = apply_row_rule(rows, ["new", "new"], {}, {}, {}, decisions)
    assert out == rows and src == ["new", "new"] and decisions == []


def test_failure_is_mapped_by_the_gates_truncated_name():
    rows = [row("Gartner Identity & Access Management Summit 2026", "x"), row("Other", "y")]
    # The gate writes CONFERENCE[:40] then a colon.
    text = "Gartner Identity & Access Management Sum: The 2026 summit is confirmed"
    assert rows_for_failure(text, rows) == [0]


def test_shared_prefix_takes_every_candidate_row():
    rows = [row("Gartner Security & Risk Management Summit EMEA 2026", "a"),
            row("Gartner Security & Risk Management Summit Japan 2026", "b"),
            row("Unrelated", "c")]
    text = "Gartner Security & Risk Management Summi: something"
    assert rows_for_failure(text, rows) == [0, 1]


def test_failure_naming_no_row_is_reported_unmapped():
    by_row, unmapped = map_failures([("5.4", "a series row somewhere")], [row("Alpha", "a")])
    assert by_row == {} and unmapped == ["[5.4] a series row somewhere"]


def test_failing_row_takes_last_weeks_version_through_the_seed_map():
    new = row("Alpha Con 2026", "up-new-a", STATUS="bad")
    prior = row("Alpha Con 2026", "up-old-a", STATUS="good")
    # Different UPSTREAM ids, same canonical event: the join must go through the map (5.4).
    up_to_canon = {"up-new-a": "canon-a", "up-old-a": "canon-a"}
    decisions = []
    out, src = apply_row_rule([new], ["new"], {0: ["[4] x"]}, {"canon-a": prior},
                              up_to_canon, decisions)
    assert out == [prior] and src == ["prior"]
    assert decisions[0]["action"] == "kept-last-week"


def test_failing_row_with_no_prior_is_held_back():
    decisions = []
    out, src = apply_row_rule([row("New Event", "up-n")], ["new"], {0: ["[R2] x"]}, {}, {},
                              decisions)
    assert out == [] and src == []
    assert decisions[0]["action"] == "held-back"


def test_prior_that_fails_too_is_held_back_not_resubstituted():
    prior = row("Alpha Con 2026", "up-a")
    decisions = [{"conference": "Alpha Con 2026", "canonical": "up-a", "reasons": [],
                  "action": "kept-last-week"}]
    out, src = apply_row_rule([prior], ["prior"], {0: ["[6] past deadline"]},
                              {"up-a": prior}, {}, decisions)
    assert out == []
    assert [d["action"] for d in decisions] == ["held-back"]


def test_invariant_output_parsing():
    out = "\n".join([
        "  [ok  ] 1  no delivered row is missing",
        "  [FAIL] 2  no undeclared extra rows   (2)",
        "            - 2026-a",
        "            - 2026-b",
        "  [warn] 8  edition matches",
        "            - ignored",
        "RESULT: 1 INVARIANT(S) VIOLATED",
        "  - 2026-hold-line  - not a failure"])
    assert invariant_failures(out) == {"2": ["2026-a", "2026-b"]}


# ---------------------------------------------------------------- identity carried (2026-09-27)
def test_import_lands_a_renamed_row_on_the_carried_id():
    from src.cfp_monitor.grounding import normalize_rows
    raw = {"EVENT_ID": "2026-world-fuel-cell-conference-2026-fukuoka-speaking",
           "CONFERENCE": "World Fuel Cell Conference 2026", "EDITION": "2026", "CITY": "Fukuoka",
           "Market": "Utility", "OPPORTUNITY_TYPE": "Speaking"}
    derived, _ = normalize_rows([dict(raw)])
    carried, _ = normalize_rows([dict(raw)], ids={raw["EVENT_ID"]: "2026-wfcc-fukuoka"})
    assert derived[0].event_id != "2026-wfcc-fukuoka"      # the rename would mint a new record
    assert carried[0].event_id == "2026-wfcc-fukuoka"      # the carried id keeps the old one


def test_rows_not_in_the_id_map_derive_exactly_as_before():
    from src.cfp_monitor.grounding import normalize_rows
    raw = {"EVENT_ID": "x", "CONFERENCE": "Alpha Con 2026", "EDITION": "2026", "CITY": "Denver",
           "Market": "Utility"}
    a, _ = normalize_rows([dict(raw)])
    b, _ = normalize_rows([dict(raw)], ids={"something-else": "zzz"})
    assert a[0].event_id == b[0].event_id


def test_identity_falls_back_to_the_ledger_one_to_one(tmp_path):
    import csv as _csv
    from scripts.weekend_import import load_identity
    (tmp_path / "M_audited.progress.txt").write_text("Old Name 2026\r\nOther 2026\r\n", encoding="utf-8")
    with open(tmp_path / "M_input.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE", "EVENT_ID_CANON"])
        w.writerow(["Old Name 2026", "canon-old"])
        w.writerow(["Other 2026", ""])
    out = [{"EVENT_ID": "new-minted-id", "CONFERENCE": "Brand New Name 2026"},
           {"EVENT_ID": "other-id", "CONFERENCE": "Other 2026"}]
    assert load_identity(tmp_path, "M", out) == {"new-minted-id": "canon-old", "other-id": ""}
    # a ledger that does not line up one-to-one is not trusted at all
    assert load_identity(tmp_path, "M", out[:1]) == {}


def test_stamp_prefers_last_weeks_page_and_refuses_stale_twins():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from stamp_input_ids import resolve
    known = {"2026-hitb-security-conference-phuket", "2026-hitb-phuket", "2026-wfes", "2027-wfes"}
    published = {"2026-hitb-security-conference-phuket", "2027-wfes"}
    final = {"wfes 2027": {"2026-wfes", "2027-wfes"}}
    seeds = {"hitb (security conference 2026)": {"2026-hitb-phuket"}}
    # a seed match to a record that is NOT on last week's page is a stale twin: refused
    assert resolve("HITB (Security Conference 2026)", "", known, [final, seeds, {}], published)[0] == ""
    # a tie on last week's page is broken by the year in the name
    assert resolve("WFES 2027", "", known, [final, seeds, {}], published)[0] == "2027-wfes"
    # an id already stamped and still known is never changed
    assert resolve("WFES 2027", "2026-wfes", known, [final, seeds, {}], published) == ("2026-wfes", "kept")


# ---------------------------------------------------------------- awards (Friday run, 2026-09-28)
def test_rows_labelled_duplicate_are_not_counted_as_missing(tmp_path):
    import csv as _csv
    import os as _os
    from scripts.weekend_import import check_research
    with open(tmp_path / "Awards_input.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE", "DUP_OF"])
        w.writerows([["A", ""], ["B", ""], ["B again", "B"]])
    with open(tmp_path / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE"])
        w.writerows([["A"], ["B"]])
    assert check_research("Awards", tmp_path, 0) is None           # 2 of 2 real rows: complete
    _os.remove(tmp_path / "Awards_audited.csv")
    assert "no research output" in check_research("Awards", tmp_path, 0)


def test_award_ids_come_from_the_awards_table_not_the_conference_seeds(tmp_path):
    import sqlite3 as _sq
    import csv as _csv
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from stamp_input_ids import build_award_sources, resolve
    db = tmp_path / "cfp_monitor.db"
    con = _sq.connect(db)
    con.execute("create table award_grounding_facts (event_id text, upstream_event_id text, name text)")
    con.execute("insert into award_grounding_facts values ('2026-ours-awards', '2026-theirs-x-awards', 'Stevie Awards')")
    con.commit(); con.close()
    with open(tmp_path / "Awards_20260905_out.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["EVENT_ID", "CONFERENCE"])
        w.writerow(["2026-theirs-x-awards", "Stevie Awards - American Business Awards"])
    known, sources = build_award_sources(tmp_path, db)
    published = set().union(*sources[0].values())
    # last week's page names it -> our id, through upstream_event_id (5.4), never the raw id
    assert resolve("Stevie Awards - American Business Awards", "", known, sources, published) \
        == ("2026-ours-awards", "last week's file")


def test_rows_the_refresh_policy_skipped_are_not_counted_as_missing_but_a_short_run_still_is(tmp_path):
    import csv as _csv
    from scripts.weekend_import import check_research
    with open(tmp_path / "Awards_input.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE", "DUP_OF", "REFRESH_SKIP"])
        w.writerows([["A", "", ""], ["B", "", "dormant (closed)"], ["C", "", "dormant (closed)"], ["D", "", ""]])
    with open(tmp_path / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE"])
        w.writerows([["A"], ["D"]])
    assert check_research("Awards", tmp_path, 0) is None            # 2 researched of 2 due: complete
    with open(tmp_path / "Awards_audited.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["CONFERENCE"])
        w.writerows([["A"]])
    assert "stopped short" in check_research("Awards", tmp_path, 0)  # one due row missing is still a short run
