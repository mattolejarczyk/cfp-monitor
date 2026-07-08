"""Offline tests for the SQLite source-of-truth store."""
from cfp_monitor.models import ConferenceResult, Fact, CFPStatus
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store, normalize_key, guess_event_past


def mk(url, name=None, dates=None, close=None, status="unclear", sub=None, pages=3):
    r = ConferenceResult(start_url=url, pages_crawled=pages)
    if name:
        r.name = Fact(value=name)
    if dates:
        r.conference_dates = Fact(value=dates)
    if close:
        r.cfp_close_date = Fact(value=close)
    if sub:
        r.submission_url = Fact(value=sub)
    r.cfp_status = CFPStatus(status)
    r.status_basis = "explicit_open"
    return r


def test_normalize_key_dedupes():
    a = normalize_key("https://www.Conf.com/")
    b = normalize_key("http://conf.com")
    assert a == b == "conf.com", (a, b)


def test_insert_then_get():
    s = Store()
    out = s.upsert(mk("https://conf.com", name="Alpha", status="open"), Quality.PASS, ["Cyber"])
    assert out.created is True
    rec = s.get("https://www.conf.com/")            # normalized lookup
    assert rec["name"] == "Alpha"
    assert rec["categories"] == "Cyber"
    assert rec["verification_status"] == "needs_verified"
    assert rec["quality"] == "PASS"
    assert rec["last_checked"] and rec["first_seen"]


def test_change_detection():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", status="open"), Quality.PASS)
    out = s.upsert(mk("https://conf.com", name="Alpha", status="open", close="2026-06-29"), Quality.PASS)
    assert out.created is False
    fields = {c.field for c in out.changes if c.type == "updated"}
    assert "cfp_close_date" in fields, out.changes
    rec = s.get("https://conf.com")
    assert rec["cfp_close_date"] == "2026-06-29"
    assert rec["last_changed"] >= rec["first_seen"]


def test_noop_recrawl_records_no_update():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", status="open", close="2026-06-29"), Quality.PASS)
    out = s.upsert(mk("https://conf.com", name="Alpha", status="open", close="2026-06-29"), Quality.PASS)
    assert out.created is False
    assert [c for c in out.changes if c.type == "updated"] == []


def test_error_recrawl_preserves_stored_facts():
    from cfp_monitor.models import ConferenceResult
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", dates="Oct 2026", close="2026-06-29", status="open"), Quality.PASS)
    # A failed/timed-out re-crawl returns an empty result: it must NOT degrade the source of truth.
    s.upsert(ConferenceResult(start_url="https://conf.com", error="per-site timeout"), Quality.ERROR)
    rec = s.get("https://conf.com")
    assert rec["name"] == "Alpha"
    assert rec["conference_dates"] == "Oct 2026"
    assert rec["cfp_close_date"] == "2026-06-29"
    assert rec["cfp_status"] == "open"           # not downgraded to the default "unclear"
    assert rec["quality"] == "ERROR"             # but we DO record that the last attempt failed


def test_partial_recrawl_keeps_old_where_new_is_blank():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", close="2026-06-29", status="open"), Quality.PASS)
    # A thin PARTIAL re-crawl finds the name but not the deadline — the deadline must survive.
    s.upsert(mk("https://conf.com", name="Alpha", close=None, status="open"), Quality.PARTIAL)
    assert s.get("https://conf.com")["cfp_close_date"] == "2026-06-29"
    # …but a real new value still applies.
    s.upsert(mk("https://conf.com", name="Alpha Renamed", close="2026-06-29", status="open"), Quality.PARTIAL)
    assert s.get("https://conf.com")["name"] == "Alpha Renamed"


def test_verified_value_not_overwritten():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", close="2026-06-29"), Quality.PASS)
    s.verify("https://conf.com", {"cfp_close_date": "2026-06-30"})
    rec = s.get("https://conf.com")
    assert rec["verification_status"] == "verified"
    assert rec["cfp_close_date"] == "2026-06-30"
    # A later crawl disagrees — must NOT overwrite the human-verified value.
    out = s.upsert(mk("https://conf.com", name="Alpha", close="2026-07-15"), Quality.PASS)
    assert "cfp_close_date" in out.preserved_verified
    rec2 = s.get("https://conf.com")
    assert rec2["cfp_close_date"] == "2026-06-30", "verified value was overwritten!"
    conflicts = [c for c in s.changes_for("https://conf.com") if c["change_type"] == "conflicts_verified"]
    assert conflicts, "expected a conflicts_verified change to be logged"


def test_past_event_helpers():
    assert guess_event_past("March 2020") is True
    assert guess_event_past("January 2099") is False
    assert guess_event_past("TBD") is None


def test_rollover_candidates():
    s = Store()
    s.upsert(mk("https://old.com", name="Old", dates="March 2020"), Quality.PASS)
    s.upsert(mk("https://future.com", name="Future", dates="2099"), Quality.PASS)
    keys = {c["key"] for c in s.rollover_candidates()}
    assert "old.com" in keys
    assert "future.com" not in keys


def test_run_lifecycle():
    s = Store()
    rid = s.start_run()
    s.finish_run(rid, {"url_count": 2, "PASS": 1, "BLOCKED": 1})
    row = dict(s.db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone())
    assert row["url_count"] == 2 and row["pass_count"] == 1 and row["blocked_count"] == 1
    assert row["finished_at"]


def test_export_shape():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", status="open", close="2026-06-29"), Quality.PASS, ["Cyber"])
    ex = s.export_dicts()
    assert len(ex) == 1
    rec = ex[0]
    for k in ("name", "url", "status", "submission_deadline", "verified", "categories"):
        assert k in rec
    assert rec["verified"] is False


def _run():
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception as e:
            bad += 1; print(f"FAIL {fn.__name__}: {e!r}")
    print(f"--- {len(fns)-bad}/{len(fns)} passed ---")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    _run()
