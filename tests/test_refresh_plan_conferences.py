"""ACT-33: the conference refresh policy in scripts/refresh_plan.py (Cybersecurity and Utility). Offline: no model, no network, no live data.
One test per group and boundary day, the rotation, every override, the guard, the failure isolation, the dry run, the apply (backup, read-back, stable second apply), and that the awards mode is unchanged."""
import csv
import json
import sqlite3
from datetime import date, timedelta

import pytest

from scripts import refresh_plan as rp

SAT = date(2026, 10, 17)                      # a Saturday
POL = dict(rp.DEFAULT_POLICY)


def fmt(d: date) -> str:
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def closed_ended(days_ago: int, status="Closed", today=SAT) -> dict:
    end = today - timedelta(days=days_ago)
    return {"STATUS": status, "CONFERENCE DATES": fmt(end), "START DATE": end.isoformat()}


def closed_ahead(days_to_start: int, today=SAT) -> dict:
    start = today + timedelta(days=days_to_start)
    return {"STATUS": "Closed", "CONFERENCE DATES": f"{start.strftime('%B')} {start.day} - {start.strftime('%B')} {start.day + 1 if start.day < 28 else start.day}, {start.year}",
            "START DATE": start.isoformat()}


def go(rec, canon="id-a", today=SAT, pol=POL):
    return rp.classify_conference(rec, canon, today, pol)


def id_with(parity_mod: int, slot: int) -> str:
    """A canonical id whose stable_hash % parity_mod == slot."""
    for i in range(500):
        if rp.stable_hash(f"id{i}") % parity_mod == slot:
            return f"id{i}"
    raise AssertionError


# ------------------------------------------------------------------ the policy and its numbers
def test_defaults_are_the_approved_numbers():
    assert POL == {"group2_after_days": 60, "group2_every_weeks": 2, "group3_check_from_days": 14, "group3_check_to_days": 21, "group4_near_days": 30, "group4_mid_days": 90,
                   "group4_mid_every_weeks": 2, "group4_far_every_weeks": 4, "guard_max_skip_share": 0.5, "cost_per_row_usd": 0.12,
                   "lean_until": 0, "lean_deadline_days": 14}


def test_the_shipped_policy_file_equals_the_defaults_and_parses():
    strip = lambda d: {k: v for k, v in d.items() if not k.startswith("lean")}      # the one-off lean week setting may be present in the file; the approved numbers may not change
    assert strip(rp.load_policy()) == strip(POL)                     # docs/operations/refresh_policy.json


def test_policy_file_changes_a_number_without_code(tmp_path):
    p = tmp_path / "pol.json"
    p.write_text(json.dumps({"_comment": "x", "group4_near_days": 14}), encoding="utf-8")
    assert rp.load_policy(p)["group4_near_days"] == 14 and rp.load_policy(p)["group2_after_days"] == 60
    assert rp.load_policy(tmp_path / "missing.json") == POL           # absent file: built-in defaults


@pytest.mark.parametrize("bad", [{"group2_after_dayz": 3}, {"group2_every_weeks": 0}, {"group2_every_weeks": 1.5}, {"guard_max_skip_share": 1.5}, {"group3_check_from_days": 30},
                                 {"group4_near_days": 99}, {"cost_per_row_usd": -1}, {"group2_after_days": "60"}])
def test_a_typo_or_a_nonsense_number_is_refused(tmp_path, bad):
    p = tmp_path / "pol.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        rp.load_policy(p)


# ------------------------------------------------------------------ group 1
@pytest.mark.parametrize("status", ["Open", "Upcoming", "Needs Verification", ""])
def test_group1_not_closed_is_researched_every_week_whatever_the_dates(status):
    for rec in (closed_ended(400, status), closed_ahead(400, ) | {"STATUS": status}, {"STATUS": status}):
        c = go(rec)
        assert c["group"] == "G1" and c["research"] is True


# ------------------------------------------------------------------ group 3: one check, day 14 to 20
@pytest.mark.parametrize("days,expected", [(1, False), (7, False), (13, False), (14, True), (20, True), (21, False), (35, False), (60, False)])
def test_group3_boundary_days(days, expected):
    c = go(closed_ended(days))
    assert c["group"] == "G3" and c["research"] is expected


def test_group3_exactly_one_saturday_per_event():
    for ended in range(1, 70):
        end = date(2026, 6, 1) + timedelta(days=ended)
        rec = {"STATUS": "Closed", "CONFERENCE DATES": fmt(end), "START DATE": end.isoformat()}
        hits = [s for s in (date(2026, 6, 6) + timedelta(days=7 * k) for k in range(45))
                if rp.classify_conference(rec, "x", s, POL)["group"] == "G3" and rp.classify_conference(rec, "x", s, POL)["research"]]
        assert len(hits) == 1, (end, hits)


# ------------------------------------------------------------------ group 2: after day 60, every two weeks
def test_group2_starts_on_day_61_and_group3_ends_on_day_60():
    assert go(closed_ended(60))["group"] == "G3" and go(closed_ended(61))["group"] == "G2"


def test_group2_rotation_is_one_week_in_two_and_stable():
    rec = closed_ended(120)
    even, odd = id_with(2, 0), id_with(2, 1)
    weeks = [SAT + timedelta(days=7 * k) for k in range(8)]
    for cid in (even, odd):
        flags = [rp.classify_conference(closed_ended(120, today=w), cid, w, POL)["research"] for w in weeks]
        assert sum(flags) == 4 and all(flags[i] != flags[i + 1] for i in range(7)), flags          # exactly alternate
    assert rp.stable_hash("abc") == rp.stable_hash("abc") == int(__import__("hashlib").sha1(b"abc").hexdigest()[:8], 16)
    a = [rp.classify_conference(closed_ended(120, today=w), even, w, POL)["research"] for w in weeks]
    b = [rp.classify_conference(closed_ended(120, today=w), odd, w, POL)["research"] for w in weeks]
    assert [x != y for x, y in zip(a, b)] == [True] * 8                                              # the two halves never research on the same Saturday
    assert rec["STATUS"] == "Closed"


def test_the_week_number_runs_on_across_new_year():
    assert rp.week_index(date(2027, 1, 2)) - rp.week_index(date(2026, 12, 26)) == 1
    assert rp.week_index(date(2026, 12, 26)) - rp.week_index(date(2026, 12, 19)) == 1


# ------------------------------------------------------------------ group 4: call closed, event ahead, by days to the START
@pytest.mark.parametrize("days", [1, 29, 30])
def test_group4_within_30_days_is_weekly(days):
    for w in range(6):
        t = SAT + timedelta(days=7 * w)
        assert rp.classify_conference(closed_ahead(days, today=t), "x", t, POL)["research"] is True


@pytest.mark.parametrize("days,every", [(31, 2), (90, 2), (91, 4), (400, 4)])
def test_group4_middle_and_far_rotation(days, every):
    cid = id_with(every, 0)
    flags = [rp.classify_conference(closed_ahead(days, today=SAT + timedelta(days=7 * k)), cid, SAT + timedelta(days=7 * k), POL)["research"] for k in range(0, 4 * every, 1)]
    # the distance is measured from each Saturday, so keep it fixed by rebuilding the row each week (done above): the rotation alone decides
    assert sum(flags) == 4 and all(g["group"] == "G4" for g in [go(closed_ahead(days), cid)])


def test_group4_boundaries_pick_the_right_band():
    assert "weekly" in go(closed_ahead(30))["reason"]
    assert "every 2 weeks" in go(closed_ahead(31))["reason"] and "every 2 weeks" in go(closed_ahead(90))["reason"]
    assert "every 4 weeks" in go(closed_ahead(91))["reason"]


def test_an_event_that_has_started_but_not_ended_is_group4_weekly():
    rec = {"STATUS": "Closed", "CONFERENCE DATES": "October 15 - October 19, 2026", "START DATE": "2026-10-15"}
    c = go(rec)
    assert c["group"] == "G4" and c["research"] is True


def test_event_end_uses_conference_dates_end_else_start_date():
    rec = {"STATUS": "Closed", "CONFERENCE DATES": "October 10 - October 20, 2026", "START DATE": "2026-10-10"}
    assert go(rec)["group"] == "G4"                                                      # still running on the 17th: not "ended"
    rec2 = {"STATUS": "Closed", "CONFERENCE DATES": "", "START DATE": "2026-09-30"}
    c = go(rec2)
    assert c["group"] == "G3" and c["end"] == date(2026, 9, 30)                           # 17 days ago: the check
    assert go({"STATUS": "Closed", "CONFERENCE DATES": "December 30 - January 2, 2027", "START DATE": "2026-12-30"})["end"] == date(2027, 1, 2)   # across the new year


def test_unreadable_or_disagreeing_dates_are_researched():
    for rec in ({"STATUS": "Closed", "CONFERENCE DATES": "TBD", "START DATE": ""}, {"STATUS": "Closed", "CONFERENCE DATES": "", "START DATE": ""},
                {"STATUS": "Closed", "CONFERENCE DATES": "March 3 - March 4, 2027", "START DATE": "2026-01-15"}):
        c = go(rec)
        assert c["research"] is True and c.get("doubt") is True and "doubt means research" in c["reason"]


def test_next_due_is_the_next_saturday_the_schedule_researches():
    assert rp.next_due(closed_ended(1), "x", SAT, POL) == (SAT + timedelta(days=14)).isoformat()      # ended 16 Oct: 24 Oct is day 8, 31 Oct is day 15 = its one check
    far = rp.next_due(closed_ahead(400), id_with(4, 0), SAT, POL)
    assert far and (date.fromisoformat(far) - SAT).days % 7 == 0


# ------------------------------------------------------------------ the plan: overrides, guard
def conf_rows(n, prefix="r"):
    return [{"CONFERENCE": f"Conf {i}", "EVENT_ID_CANON": f"{prefix}{i}", "DUP_OF": ""} for i in range(n)]


def dormant_prior(i, today=SAT):
    return {"STATUS": "Closed", "CONFERENCE DATES": fmt(today - timedelta(days=30)), "START DATE": (today - timedelta(days=30)).isoformat(),
            "CONFERENCE URL": f"https://c{i}.example/", "SUBMISSION URL": ""}


def plan_for(rows, priors, states=None, overrides=None, today=SAT, pol=None):
    return rp.conference_plan(rows, priors, states or {}, overrides or set(), today, pol or {**POL, "guard_max_skip_share": 1.0})


def test_a_dormant_row_is_skipped_and_marked_with_group_and_next_check():
    rows = conf_rows(2)
    pl = plan_for(rows, {"r0": dormant_prior(0), "r1": closed_ended(15)})
    assert 0 in pl["skip"] and pl["skip"][0].startswith("G3 dormant") and "next check 2026-" in pl["skip"][0]
    assert 1 not in pl["skip"]                                                  # ended 15 days ago: this is its one check


def test_override_new_event_no_prior_row_is_never_skipped():
    pl = plan_for(conf_rows(2), {"r0": dormant_prior(0)})
    assert 1 not in pl["skip"] and pl["decisions"][1]["override"] == "new" and pl["counts"]["overrides"] == 1


def test_override_row_with_no_id_is_never_skipped():
    rows = conf_rows(1)
    rows[0]["EVENT_ID_CANON"] = ""
    assert plan_for(rows, {})["skip"] == {}


def test_override_dead_link_in_link_checks_forces_research():
    pl = plan_for(conf_rows(2), {"r0": dormant_prior(0), "r1": dormant_prior(1)}, states={"https://c0.example/": "dead", "https://c1.example/": "alive"})
    assert 0 not in pl["skip"] and "recorded dead" in pl["decisions"][0]["reason"] and pl["decisions"][0]["override"] == "dead-link"
    assert 1 in pl["skip"]


def test_override_dead_link_on_any_customer_facing_column():
    p = dormant_prior(0) | {"SUBMISSION URL": "https://cfp.example/", "SPONSOR_URL": "https://sp.example/"}
    for url in ("https://cfp.example/", "https://sp.example/"):
        assert plan_for(conf_rows(1), {"r0": p}, states={url: "dead"})["skip"] == {}


def test_override_named_in_the_overrides_file(tmp_path):
    f = tmp_path / "ov.txt"
    f.write_text("# why\n\nr0   # customer flag\n", encoding="utf-8")
    assert rp.read_overrides(f) == {"r0"} and rp.read_overrides(tmp_path / "none.txt") == set()
    pl = plan_for(conf_rows(2), {"r0": dormant_prior(0), "r1": dormant_prior(1)}, overrides=rp.read_overrides(f))
    assert 0 not in pl["skip"] and 1 in pl["skip"] and pl["decisions"][0]["override"] == "named"


def test_the_shipped_overrides_file_is_empty_but_for_comments():
    assert rp.read_overrides() == set()


def test_override_first_saturday_of_january_researches_everything():
    jan = date(2027, 1, 2)
    pl = plan_for(conf_rows(3), {f"r{i}": dormant_prior(i, jan) for i in range(3)}, today=jan)
    assert pl["skip"] == {} and pl["counts"]["overrides"] == 3
    assert rp.first_saturday_of_january(date(2027, 1, 2)) and not rp.first_saturday_of_january(date(2027, 1, 9)) and not rp.first_saturday_of_january(date(2026, 12, 26))
    nxt = date(2027, 1, 9)
    assert len(plan_for(conf_rows(3), {f"r{i}": dormant_prior(i, nxt) for i in range(3)}, today=nxt)["skip"]) == 3


def test_dup_of_rows_are_left_to_the_audit():
    rows = conf_rows(2)
    rows[1]["DUP_OF"] = "r0"
    pl = plan_for(rows, {"r0": dormant_prior(0), "r1": dormant_prior(1)})
    assert pl["rows"] == 1 and list(pl["skip"]) == [0]


def test_guard_skips_nothing_when_the_plan_would_skip_over_the_share():
    rows = conf_rows(10)
    priors = {f"r{i}": dormant_prior(i) for i in range(10)}
    pl = rp.conference_plan(rows, priors, {}, set(), SAT, POL)                  # all 10 would be skipped: 100 percent
    assert pl["skip"] == {} and "GUARD" in pl["fuse"] and pl["researched"] == 10
    pl = rp.conference_plan(rows + conf_rows(10, "n"), {**priors}, {}, set(), SAT, POL)      # 10 skipped of 20 (the 10 new ones are never skipped): exactly 50 percent is allowed
    assert len(pl["skip"]) == 10 and pl["fuse"] == ""
    pl = rp.conference_plan(rows + conf_rows(9, "n"), {**priors}, {}, set(), SAT, POL)       # 10 of 19: over 50 percent
    assert pl["skip"] == {} and "GUARD" in pl["fuse"]
    assert "GUARD" in rp.summary_line("Cybersecurity", pl, POL) and ", 0 skipped" in rp.summary_line("Cybersecurity", pl, POL)


def test_dry_run_line_says_nothing_was_marked():
    pl = plan_for(conf_rows(1), {"r0": dormant_prior(0)})
    assert rp.summary_line("Utility", pl, POL, dry=True).endswith("[DRY RUN: nothing was marked, so every row is researched this week]")
    assert "DRY RUN" not in rp.summary_line("Utility", pl, POL)


def test_guard_share_is_a_setting():
    rows = conf_rows(10)
    priors = {f"r{i}": dormant_prior(i) for i in range(10)}
    assert len(rp.conference_plan(rows, priors, {}, set(), SAT, {**POL, "guard_max_skip_share": 1.0})["skip"]) == 10
    assert rp.conference_plan(rows, priors, {}, set(), SAT, {**POL, "guard_max_skip_share": 0.9})["skip"] == {}


def test_summary_line_format_and_saving_estimate():
    rows = conf_rows(4) + conf_rows(1, "n")
    priors = {"r0": dormant_prior(0), "r1": dormant_prior(1), "r2": {"STATUS": "Open", "CONFERENCE DATES": "", "START DATE": ""}, "r3": closed_ended(1)}
    pl = plan_for(rows, priors)
    line = rp.summary_line("Cybersecurity", pl, POL)
    assert line == "REFRESH-PLAN Cybersecurity: 5 rows, 2 researched (g1 1, g2 0, g3 0, g4 0, overrides 1), 3 skipped (saving about 0.36 USD, an estimate)"


# ------------------------------------------------------------------ end to end on files
def make_world(tmp_path, n_dormant=6, n_live=10):
    mk = tmp_path / "Markets"
    mk.mkdir()
    cols = ["CONFERENCE", "STATUS", "EVENT_ID_CANON", "DUP_OF", "SUBMISSION URL"]
    rows = [{"CONFERENCE": f"D{i}", "STATUS": "Closed", "EVENT_ID_CANON": f"d{i}", "DUP_OF": "", "SUBMISSION URL": "x"} for i in range(n_dormant)]
    rows += [{"CONFERENCE": f"L{i}", "STATUS": "Open", "EVENT_ID_CANON": f"l{i}", "DUP_OF": "", "SUBMISSION URL": "y"} for i in range(n_live)]
    with open(mk / "Utility_input.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    fcols = ["EVENT_ID", "CONFERENCE", "STATUS", "CONFERENCE DATES", "START DATE", "CONFERENCE URL", "SUBMISSION URL"]
    d = SAT - timedelta(days=30)
    final = [{"EVENT_ID": f"up-d{i}", "CONFERENCE": f"D{i}", "STATUS": "Closed", "CONFERENCE DATES": fmt(d), "START DATE": d.isoformat(), "CONFERENCE URL": f"https://d{i}.example/", "SUBMISSION URL": ""} for i in range(n_dormant)]
    final += [{"EVENT_ID": f"up-l{i}", "CONFERENCE": f"L{i}", "STATUS": "Open", "CONFERENCE DATES": "", "START DATE": "", "CONFERENCE URL": "", "SUBMISSION URL": ""} for i in range(n_live)]
    with open(mk / "Utility_audited.final.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fcols)
        w.writeheader()
        w.writerows(final)
    live = tmp_path / "live"
    (live / "market_sheets").mkdir(parents=True)
    with open(live / "market_sheets" / "utility_seed.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["EVENT_ID", "EVENT_ID_CANON"])
        w.writeheader()
        w.writerows([{"EVENT_ID": f"up-{k}", "EVENT_ID_CANON": k} for k in [f"d{i}" for i in range(n_dormant)] + [f"l{i}" for i in range(n_live)]])
    db = live / "cfp_monitor.db"
    con = sqlite3.connect(db)
    con.execute("create table link_checks (url, state, checked_at, http_status, first_seen, last_alive)")
    con.execute("insert into link_checks values ('https://d0.example/', 'dead', '2026-10-10', null, '2026-10-01', null)")
    con.commit()
    con.close()
    return mk, db


def run_main(mk, db, tmp_path, *extra, today="2026-10-17", market="Utility"):
    # These tests exercise the NORMAL policy. The shipped docs/operations/refresh_policy.json may carry a one-off lean week (lean_until), so unless a test passes its own policy,
    # it gets an empty one (all built-in defaults, lean off).
    if "--policy" not in extra:
        (tmp_path / "policy_defaults.json").write_text("{}", encoding="utf-8")
        extra = (*extra, "--policy", str(tmp_path / "policy_defaults.json"))
    return rp.main(["--market", market, "--markets-dir", str(mk), "--db", str(db), "--today", today, "--out-dir", str(tmp_path / "out"), "--min-mapped", "1", *extra])


@pytest.fixture
def world(tmp_path):
    mk, db = make_world(tmp_path)
    return mk, db, tmp_path


def snapshot(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()}


def test_dry_run_writes_only_the_report(world, capsys):
    mk, db, tmp = world
    before_inputs, before_db = snapshot(mk), db.read_bytes()
    assert run_main(mk, db, tmp) == 0
    out = capsys.readouterr().out
    assert out.startswith("REFRESH-PLAN Utility: 16 rows, 11 researched") and "[DRY RUN" in out and "dry run: the input list was not changed" in out
    assert snapshot(mk) == before_inputs and db.read_bytes() == before_db                       # nothing but the report changed
    assert sorted(p.name for p in (tmp / "out").iterdir()) == ["refresh_plan_Utility.csv", "refresh_plan_Utility.md"]
    rows = list(csv.DictReader(open(tmp / "out" / "refresh_plan_Utility.csv", encoding="utf-8")))
    assert len(rows) == 16 and {r["decision"] for r in rows} == {"research", "skip"}
    d0 = next(r for r in rows if r["canonical_id"] == "d0")
    assert d0["decision"] == "research" and d0["override"] == "dead-link"                        # d0's link is recorded dead
    d1 = next(r for r in rows if r["canonical_id"] == "d1")
    assert d1["group"] == "G3" and d1["decision"] == "skip" and "2026-11-21" <= d1["next_due_saturday"] <= "2026-11-28"


def test_apply_marks_only_the_refresh_skip_column_with_backup_and_readback(world, capsys):
    mk, db, tmp = world
    inp = mk / "Utility_input.csv"
    original = list(csv.DictReader(open(inp, encoding="utf-8")))
    assert run_main(mk, db, tmp, "--apply") == 0
    assert "read-back proof OK" in capsys.readouterr().out
    after = list(csv.DictReader(open(inp, encoding="utf-8")))
    assert len(after) == len(original)
    for o, a in zip(original, after):
        assert {k: v for k, v in a.items() if k != "REFRESH_SKIP"} == o
    marked = {r["EVENT_ID_CANON"] for r in after if r["REFRESH_SKIP"]}
    assert marked == {"d1", "d2", "d3", "d4", "d5"}                                              # d0 has a dead link; the live rows are group 1
    assert (mk / "Utility_input.pre-refresh.csv").exists()
    assert list(csv.DictReader(open(mk / "Utility_input.pre-refresh.csv", encoding="utf-8"))) == original


def test_second_apply_is_stable(world):
    mk, db, tmp = world
    run_main(mk, db, tmp, "--apply")
    first = (mk / "Utility_input.csv").read_bytes()
    run_main(mk, db, tmp, "--apply")
    assert (mk / "Utility_input.csv").read_bytes() == first


def test_marks_move_with_the_plan_and_a_week_later_the_row_is_not_marked(world):
    mk, db, tmp = world
    run_main(mk, db, tmp, "--apply")
    run_main(mk, db, tmp, "--apply", today="2026-10-31")                                         # day 44 of d*: still skipped, none due
    marked = {r["EVENT_ID_CANON"] for r in csv.DictReader(open(mk / "Utility_input.csv", encoding="utf-8")) if r["REFRESH_SKIP"]}
    assert marked == {"d1", "d2", "d3", "d4", "d5"}
    # ended 30 days before 17 Oct = 17 Sep; on 31 Oct that is day 44 (skip); on 7 Nov day 51; on 14 Nov day 58; on 21 Nov day 65 -> group 2 rotation
    run_main(mk, db, tmp, "--apply", today="2026-11-21")
    rows = list(csv.DictReader(open(mk / "Utility_input.csv", encoding="utf-8")))
    marks = [r["REFRESH_SKIP"] for r in rows if r["REFRESH_SKIP"]]
    assert marks and all(m.startswith("G2") for m in marks) and {r["EVENT_ID_CANON"] for r in rows if r["REFRESH_SKIP"]} <= {"d1", "d2", "d3", "d4", "d5"}


def test_readback_failure_puts_the_file_back(world, monkeypatch):
    mk, db, tmp = world
    inp = mk / "Utility_input.csv"
    before = inp.read_bytes()
    monkeypatch.setattr(rp, "verify_marks", lambda *a, **k: "row 3: column CONFERENCE changed")
    with pytest.raises(RuntimeError):
        rp.apply_conference_marks(inp, {0: "G2 x"})
    assert inp.read_bytes() == before


def test_verify_marks_catches_a_changed_cell_and_a_wrong_mark(tmp_path):
    p = tmp_path / "i.csv"
    p.write_text('"CONFERENCE","REFRESH_SKIP"\n"A","m"\n"B",""\n', encoding="utf-8")
    before = [{"CONFERENCE": "A"}, {"CONFERENCE": "B"}]
    assert rp.verify_marks(p, before, {0: "m"}) is None
    assert "not what was intended" in rp.verify_marks(p, before, {1: "m"})
    assert "changed" in rp.verify_marks(p, [{"CONFERENCE": "A2"}, {"CONFERENCE": "B"}], {0: "m"})
    assert "row count" in rp.verify_marks(p, before[:1], {0: "m"})


def test_any_exception_means_skip_nothing_and_exit_zero(world, capsys):
    mk, db, tmp = world
    (mk / "Utility_audited.final.csv").unlink()                                                 # nothing to carry: nothing may be skipped
    assert run_main(mk, db, tmp) == 0
    out = capsys.readouterr().out
    assert out.startswith("REFRESH-PLAN Utility: UNKNOWN - FileNotFoundError") and "every row will be researched" in out


def test_a_failed_apply_clears_older_marks_so_the_week_researches_everything(world, capsys):
    mk, db, tmp = world
    run_main(mk, db, tmp, "--apply")
    assert any(r["REFRESH_SKIP"] for r in csv.DictReader(open(mk / "Utility_input.csv", encoding="utf-8")))
    (mk / "Utility_audited.final.csv").unlink()
    assert run_main(mk, db, tmp, "--apply") == 0
    assert not any(r["REFRESH_SKIP"] for r in csv.DictReader(open(mk / "Utility_input.csv", encoding="utf-8")))
    assert "UNKNOWN" in capsys.readouterr().out


def test_bad_policy_file_is_isolated(world, capsys, tmp_path):
    mk, db, tmp = world
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert run_main(mk, db, tmp, "--policy", str(bad)) == 0
    assert "UNKNOWN" in capsys.readouterr().out
    assert run_main(mk, db, tmp, "--market", "Utility", today="not-a-date") == 0                 # even a bad date argument never raises


def test_unmapped_ids_stop_the_plan(world, capsys):
    mk, db, tmp = world
    assert rp.main(["--market", "Utility", "--markets-dir", str(mk), "--db", str(db), "--today", "2026-10-17", "--out-dir", str(tmp / "o"), "--min-mapped", "9999"]) == 0
    assert "UNKNOWN" in capsys.readouterr().out


def test_stale_marks_are_warned_about_in_a_dry_run(world, capsys):
    mk, db, tmp = world
    run_main(mk, db, tmp, "--apply")
    capsys.readouterr()
    run_main(mk, db, tmp)
    out = capsys.readouterr().out
    assert "dry run" in out and "still carry an older REFRESH_SKIP mark" in out


def test_clear_removes_every_mark(world, capsys):
    mk, db, tmp = world
    run_main(mk, db, tmp, "--apply")
    run_main(mk, db, tmp, "--clear")
    assert not any(r["REFRESH_SKIP"] for r in csv.DictReader(open(mk / "Utility_input.csv", encoding="utf-8")))
    assert "cleared every REFRESH_SKIP mark" in capsys.readouterr().out


# ------------------------------------------------------------------ awards unchanged
def test_awards_mode_is_unchanged(tmp_path, capsys):
    inp = tmp_path / "Awards_input.csv"
    inp.write_text('"CONFERENCE","EVENT_ID_CANON"\n"A","a"\n', encoding="utf-8")
    db = tmp_path / "c.db"
    con = sqlite3.connect(db)
    con.execute("create table award_grounding_facts (event_id, status, deadline, submission_opens, source_as_of)")
    con.execute("insert into award_grounding_facts values ('a','Open','','','2026-10-01')")
    con.commit()
    con.close()
    assert rp.main(["--market", "Awards", "--markets-dir", str(tmp_path), "--db", str(db), "--today", "2026-10-09"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("refresh_plan Awards 2026-10-09: 1 awards, research 1, skip 0 (0%); researched because: live 1") and "report only: nothing written" in out
    assert "REFRESH-PLAN" not in out and inp.read_text(encoding="utf-8") == '"CONFERENCE","EVENT_ID_CANON"\n"A","a"\n'


# ------------------------------------------------------------------ LEAN WEEK (operator, 2026-10-19): a one-off that researches only what cannot wait
LEAN = {**POL, "lean_until": 20261024, "_lean": True, "guard_max_skip_share": 0.5}


def live_prior(i, deadline_in_days=None, status="Open", today=SAT):
    p = {"STATUS": status, "CONFERENCE DATES": fmt(today + timedelta(days=120)), "START DATE": (today + timedelta(days=120)).isoformat(),
         "CONFERENCE URL": f"https://l{i}.example/", "SUBMISSION URL": "", "SUBMISSION DEADLINE": ""}
    if deadline_in_days is not None:
        p["SUBMISSION DEADLINE"] = (today + timedelta(days=deadline_in_days)).isoformat()
    return p


def test_lean_week_is_in_force_until_its_date_and_then_expires_by_itself():
    pol = {**POL, "lean_until": 20261024}
    assert rp.lean_active(pol, date(2026, 10, 24)) and rp.lean_active(pol, date(2026, 10, 17))
    assert not rp.lean_active(pol, date(2026, 10, 25)) and not rp.lean_active(pol, date(2026, 10, 31))
    assert not rp.lean_active(POL, SAT)                                      # off by default (lean_until = 0)
    assert isinstance(rp.load_policy()["lean_until"], int)                   # the shipped file loads with the new numeric keys


def test_normal_weeks_are_unchanged_by_the_lean_code():
    pl = plan_for(conf_rows(2), {"r0": live_prior(0, 100), "r1": dormant_prior(1)})
    assert 0 not in pl["skip"] and 1 in pl["skip"]


def test_lean_researches_only_a_deadline_within_the_window_a_new_event_a_live_dead_link_and_named_rows():
    rows = conf_rows(8)
    priors = {"r0": live_prior(0, 3), "r1": live_prior(1, 14), "r2": live_prior(2, 15), "r3": live_prior(3, 90), "r4": live_prior(4, None),
              "r5": live_prior(5, 90) | {"CONFERENCE URL": "https://dead.example/"}, "r6": dormant_prior(6) | {"CONFERENCE URL": "https://dead2.example/"}}
    pl = plan_for(rows, priors, states={"https://dead.example/": "dead", "https://dead2.example/": "dead"}, overrides={"r4"}, pol=LEAN)
    researched = {d["canonical"] for d in pl["decisions"] if d["research"]}
    assert researched == {"r0", "r1", "r5", "r4", "r7"}, researched      # r0 r1 deadline in window; r5 live+dead link; r4 named; r7 new (no prior)
    assert {"r2", "r3", "r6"} <= {d["canonical"] for d in pl["decisions"] if not d["research"]}
    assert pl["decisions"][6]["reason"].startswith("LEAN WEEK")


def test_lean_week_skips_a_row_with_unreadable_dates_that_the_normal_schedule_would_research():
    odd = {"STATUS": "Closed", "CONFERENCE DATES": "", "START DATE": "", "SUBMISSION DEADLINE": ""}
    assert plan_for(conf_rows(1), {"r0": odd}, pol={**LEAN, "guard_max_skip_share": 1.0})["skip"].get(0)
    assert plan_for(conf_rows(1), {"r0": odd})["skip"] == {}                                   # normal week: doubt means research


def test_lean_week_relaxes_the_guard_but_still_has_one():
    rows = conf_rows(40)
    priors = {f"r{i}": live_prior(i, 90) for i in range(40)}
    pl0 = plan_for(rows, priors, pol=LEAN)
    assert pl0["skip"] == {} and "GUARD" in pl0["fuse"]                                         # 100 percent skipped is over even the lean guard: nothing skipped
    rows2 = conf_rows(100)
    priors2 = {f"r{i}": live_prior(i, 90) for i in range(97)} | {f"r{i}": live_prior(i, 3) for i in range(97, 100)}
    pl = plan_for(rows2, priors2, pol=LEAN)
    assert len(pl["skip"]) == 97 and pl["fuse"] == ""                                           # 97 percent skipped: allowed in a lean week


def test_next_due_ignores_the_lean_flag():
    assert rp.next_due(closed_ended(1), "x", SAT, {**POL, "_lean": True}) == (SAT + timedelta(days=14)).isoformat()


def test_the_summary_line_says_it_is_a_lean_week():
    pl = plan_for(conf_rows(2), {"r0": live_prior(0, 90), "r1": live_prior(1, 3)}, pol={**LEAN, "guard_max_skip_share": 1.0})
    assert "LEAN WEEK" in rp.summary_line("Cybersecurity", pl, LEAN)
