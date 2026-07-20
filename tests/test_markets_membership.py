"""Offline tests for many-to-many market membership.

Regression cover for a real defect: `industry` was a single column, so an event on several
market lists (CES is on Consumer Electronics, Utility AND Robotics) kept only whichever list
was crawled last. A PR client filtering "Robotics" then missed CES entirely.
"""
from cfp_monitor.models import CFPStatus, ConferenceResult, Fact
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store


def mk(url, name=None, industry=None, status="open"):
    r = ConferenceResult(start_url=url)
    if name:
        r.name = Fact(value=name)
    r.industry = industry
    r.cfp_status = CFPStatus(status)
    return r


def test_event_on_several_lists_keeps_every_market():
    s = Store()
    for market in ("Consumer Electronics", "Utility", "Robotics"):
        s.upsert(mk("https://www.ces.tech", name="CES 2027", industry=market),
                 Quality.PASS, source_list=f"{market} list")
    assert s.markets_for("https://www.ces.tech") == ["Consumer Electronics", "Robotics", "Utility"]
    # one canonical record, not three
    assert len(s.all_records()) == 1


def test_each_market_filter_finds_the_shared_event_independently():
    s = Store()
    for market in ("Consumer Electronics", "Utility"):
        s.upsert(mk("https://www.ces.tech", name="CES 2027", industry=market), Quality.PASS)
    s.upsert(mk("https://robobusiness.com", name="RoboBusiness", industry="Robotics"), Quality.PASS)
    exports = {e["name"]: e for e in s.export_dicts()}
    assert "Consumer Electronics" in exports["CES 2027"]["markets"]
    assert "Utility" in exports["CES 2027"]["markets"]          # both, independently
    assert exports["RoboBusiness"]["markets"] == ["Robotics"]


def test_membership_is_never_removed_by_a_failed_recrawl():
    s = Store()
    s.upsert(mk("https://www.ces.tech", name="CES", industry="Utility"), Quality.PASS)
    # a later failed crawl carrying no industry must not strip the membership
    s.upsert(mk("https://www.ces.tech", industry=None), Quality.ERROR)
    assert s.markets_for("https://www.ces.tech") == ["Utility"]


def test_membership_recorded_even_when_that_crawl_errored():
    """The event is on that market's list regardless of whether this crawl succeeded."""
    s = Store()
    s.upsert(mk("https://slow.example", industry="Semiconductor"), Quality.ERROR)
    assert s.markets_for("https://slow.example") == ["Semiconductor"]


def test_repeat_runs_do_not_duplicate_membership():
    s = Store()
    for _ in range(3):
        s.upsert(mk("https://a.example", industry="Robotics"), Quality.PASS)
    assert s.markets_for("https://a.example") == ["Robotics"]


def test_all_markets_lists_every_market_in_use():
    s = Store()
    s.upsert(mk("https://a.example", industry="Robotics"), Quality.PASS)
    s.upsert(mk("https://b.example", industry="Utility"), Quality.PASS)
    s.upsert(mk("https://a.example", industry="Utility"), Quality.PASS)
    assert s.all_markets() == ["Robotics", "Utility"]


def test_blank_industry_creates_no_membership():
    s = Store()
    for blank in (None, "", "   "):
        s.upsert(mk(f"https://x{blank!r}.example", industry=blank), Quality.PASS)
    assert s.all_markets() == []


def test_legacy_industry_column_is_backfilled_into_memberships():
    """A DB written before the join table existed must not lose its labels."""
    s = Store()
    s.upsert(mk("https://legacy.example", name="Legacy", industry="Utility"), Quality.PASS)
    # simulate a pre-migration DB: membership row gone, legacy column still set
    s.db.execute("DELETE FROM conference_markets")
    s.db.commit()
    assert s.markets_for("https://legacy.example") == []
    s._migrate()                                   # runs on every open
    s.db.commit()
    assert s.markets_for("https://legacy.example") == ["Utility"]
