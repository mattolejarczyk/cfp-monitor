"""Offline tests for the customer-feed export."""
import csv
import json
import os
import tempfile

from cfp_monitor.models import ConferenceResult, Fact, CFPStatus
from cfp_monitor.quality_gate import Quality
from cfp_monitor.storage import Store
from cfp_monitor.export import export_rows, write_feed


def _mk(url, name):
    r = ConferenceResult(start_url=url, pages_crawled=3)
    r.name = Fact(value=name)
    r.cfp_status = CFPStatus("open")
    return r


def _seed(db):
    s = Store(db)
    run = s.start_run()
    s.upsert(_mk("https://a.com", "Alpha"), Quality.PASS, ["Cyber"], run)
    s.upsert(_mk("https://b.com", "Beta"), Quality.PASS, ["Hydrogen"], run)
    s.close()


def test_write_feed():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    _seed(db)
    res = write_feed(db, os.path.join(d, "feed"))
    assert res["count"] == 2
    with open(res["csv"], encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][0] == "CONFERENCE" and len(rows) == 3
    j = json.load(open(res["json"], encoding="utf-8"))
    assert j["columns"][0] == "CONFERENCE" and len(j["rows"]) == 2


def test_tag_filter():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    _seed(db)
    assert len(export_rows(db, tag="cyber")) == 1
    assert len(export_rows(db, tag="hydrogen")) == 1
    assert len(export_rows(db)) == 2


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
