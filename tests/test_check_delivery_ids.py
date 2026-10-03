"""scripts/check_delivery_ids.py: an id upstream sends must be traced to where we hold it."""
from scripts.check_delivery_ids import locate


def test_unknown_known_and_not_queued():
    src = {"database": {"2026-a-houston"}, "this week's research": set(), "approved file": {"2026-a-houston"}, "input list": set()}
    res = {r["id"]: r for r in locate(["2026-a-houston-speaking", "2026-a-houston", "ghost"], src, {})}
    assert res["2026-a-houston-speaking"]["unknown"]                      # their spelling is not ours: UNKNOWN, not guessed
    assert res["2026-a-houston"]["not_queued"] and not res["2026-a-houston"]["unknown"]
    assert res["ghost"]["unknown"]


def test_translation_through_the_seed_map():
    src = {"database": {"2026-a-houston"}, "input list": {"2026-a-houston"}}
    r = locate(["up-1"], src, {"up-1": "2026-a-houston"})[0]
    assert not r["unknown"] and not r["not_queued"] and r["canonical"] == "2026-a-houston"
