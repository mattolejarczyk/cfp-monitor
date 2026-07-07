"""Offline tests for in-app sheet editing: direct human fields, correction-precedence,
the verified flag, the notes migration, and the customer CSV text helper."""
from cfp_monitor.models import ConferenceResult, Fact, CFPStatus
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store
from cfp_monitor.customer_format import to_customer_csv_text, CUSTOMER_HEADERS


def mk(url, name=None, close=None, status="unclear"):
    r = ConferenceResult(start_url=url)
    if name:
        r.name = Fact(value=name)
    if close:
        r.cfp_close_date = Fact(value=close)
    r.cfp_status = CFPStatus(status)
    r.status_basis = "explicit_open"
    return r


def test_notes_column_and_set_fields():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha"), Quality.PASS)
    s.set_fields("https://conf.com", {"priority": "High", "notes": "call the organizer", "coordinator_email": "a@b.com"})
    rec = s.get("https://conf.com")
    assert rec["priority"] == "High"
    assert rec["notes"] == "call the organizer"          # migrated column persists
    assert rec["coordinator_email"] == "a@b.com"


def test_set_fields_rejects_unknown_columns():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha"), Quality.PASS)
    s.set_fields("https://conf.com", {"cfp_status": "hacked", "bogus": "x"})   # not in whitelist
    rec = s.get("https://conf.com")
    assert rec["cfp_status"] == "unclear"                # unchanged (not a plain-editable col)


def test_correct_survives_future_crawl():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", status="unclear"), Quality.PASS)
    s.correct("https://conf.com", {"cfp_close_date": "2026-06-29", "cfp_status": "open"})
    assert s.get("https://conf.com")["cfp_close_date"] == "2026-06-29"
    # A later crawl disagreeing must NOT overwrite the human value (correction-precedence).
    s.upsert(mk("https://conf.com", name="Alpha", close="2099-01-01", status="closed"), Quality.PASS)
    rec = s.get("https://conf.com")
    assert rec["cfp_close_date"] == "2026-06-29"
    assert rec["cfp_status"] == "open"


def test_correct_does_not_flip_verified_flag():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha"), Quality.PASS)
    s.correct("https://conf.com", {"cfp_close_date": "2026-06-29"})
    assert s.get("https://conf.com")["verification_status"] == "needs_verified"


def test_set_verified_toggle():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha"), Quality.PASS)
    s.set_verified("https://conf.com", True)
    assert s.get("https://conf.com")["verification_status"] == "verified"
    s.set_verified("https://conf.com", False)
    assert s.get("https://conf.com")["verification_status"] == "needs_verified"


def test_customer_csv_text():
    s = Store()
    s.upsert(mk("https://conf.com", name="Alpha", status="open"), Quality.PASS, ["Cyber"])
    text = to_customer_csv_text(s.export_dicts())
    lines = text.splitlines()
    assert lines[0].startswith(",".join(CUSTOMER_HEADERS[:2]))   # CONFERENCE,CONFERENCE URL,...
    assert "Alpha" in text and "https://conf.com" in text


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
