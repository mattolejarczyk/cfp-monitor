"""ACT-17: a carried value keeps the date it was last confirmed, and the load QA flags one carried longer than the limit."""
from datetime import date

from scripts.carry_age import LIMIT_WEEKS, carried_units, load_ledger, save_ledger, stale, unit_of, update_ledger
from scripts.post_load_qa import build, carry_age_section

T0 = date(2026, 10, 10)
PRIOR = {"c1": {"SOURCE_AS_OF": "2026-08-01"}, "c2": {"SOURCE_AS_OF": "2026-10-03"}}


def _carried():
    ov = {"overlaid": [{"conference": "Alpha", "canonical": "c1", "fields": ["ORGANIZER", "CITY", "DEADLINE_QUOTE", "IS_PROJECTED"]},
                       {"conference": "Beta", "canonical": "c2", "fields": ["CITY"]}]}
    sp = {"carried": [{"conference": "Alpha", "canonical": "c1", "fields": ["SPONSOR_URL"]}]}
    return carried_units(ov, sp, PRIOR)


def test_units_and_the_first_confirmation_date_come_from_the_prior_row():
    assert [unit_of(f) for f in ("ORGANIZER", "DEADLINE_QUOTE", "SPONSOR_COST", "CITY")] == ["organizer", "evidence", "sponsorship", ""]
    c = _carried()
    assert set(c) == {"c1"}                                  # c2 carried only CITY: not aged
    assert c["c1"]["units"] == {"organizer": "2026-08-01", "evidence": "2026-08-01", "sponsorship": "2026-08-01"}


def test_a_carried_value_keeps_its_date_and_a_fresh_one_is_dropped():
    led = update_ledger({}, T0, _carried(), {"c1", "c2"})
    assert led["c1"]["units"]["evidence"] == {"confirmed": "2026-08-01", "last_carried": "2026-10-10"}
    nxt = date(2026, 10, 17)
    led2 = update_ledger(led, nxt, _carried(), {"c1"})                      # carried again: the confirmation date does NOT move
    assert led2["c1"]["units"]["evidence"] == {"confirmed": "2026-08-01", "last_carried": "2026-10-17"}
    led3 = update_ledger(led2, date(2026, 10, 24), {"c1": {"name": "Alpha", "units": {"organizer": "2026-08-01"}}}, {"c1"})
    assert set(led3["c1"]["units"]) == {"organizer"}                         # evidence and sponsorship came back fresh: dropped
    led4 = update_ledger(led3, date(2026, 10, 31), {}, {"c1"})
    assert "c1" not in led4                                                  # nothing carried: no entry
    assert "c1" in update_ledger(led3, date(2026, 10, 31), {}, {"zzz"})      # not researched this week: left as it was


def test_unknown_prior_date_starts_today_and_never_flags_at_once():
    led = update_ledger({}, T0, carried_units({"overlaid": [{"conference": "N", "canonical": "n", "fields": ["ORGANIZER"]}]}, {}, {"n": {}}), {"n"})
    assert led["n"]["units"]["organizer"]["confirmed"] == "2026-10-10" and not stale(led, T0)


def test_stale_flags_only_values_older_than_the_limit():
    led = update_ledger({}, T0, _carried(), {"c1"})                          # confirmed 2026-08-01: 10 weeks before 10-10
    old = stale(led, T0)
    assert {x["unit"] for x in old} == {"organizer", "evidence", "sponsorship"} and old[0]["weeks"] == 10
    assert not stale(led, date(2026, 9, 5))                                  # 5 weeks: inside the limit
    assert LIMIT_WEEKS == 6


def test_the_load_report_lists_and_flags_old_carried_values():
    led = update_ledger({}, T0, _carried(), {"c1"})
    rows, flags = carry_age_section(led, T0)
    assert len(rows) == 3 and any("evidence value(s) last confirmed more than 6 weeks ago" in f and "Alpha" in f for f in flags)
    rep = build({}, {}, {}, {}, "", T0, None, None, "conference", None, led)
    assert any("Carried values not re-confirmed" in s["title"] for s in rep["sections"])
    assert any("carried organizer value(s)" in f for f in rep["flags"])
    rep2 = build({}, {}, {}, {}, "", T0, None, None, "conference", None, {})
    assert not any("carried" in f for f in rep2["flags"])


def test_ledger_round_trip(tmp_path):
    p = tmp_path / "carry_ledger.json"
    assert load_ledger(p) == {}
    led = update_ledger({}, T0, _carried(), {"c1"})
    save_ledger(p, led)
    assert load_ledger(p) == led
