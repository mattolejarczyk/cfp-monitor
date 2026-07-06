"""Offline tests for the coverage report formatter."""
from cfp_monitor.coverage import coverage_markdown, coverage_csv_rows

ROWS = [
    {"url": "https://a.com", "verdict": "PASS", "reason": "core facts", "name": "A Conf", "canonical": "https://a.com"},
    {"url": "https://b.com", "verdict": "PARTIAL", "reason": "thin content", "name": "", "canonical": "https://b.com"},
    {"url": "https://c.com", "verdict": "BLOCKED", "reason": "anti-bot / refused status 403", "name": "", "canonical": ""},
    {"url": "https://d.com", "verdict": "ERROR", "reason": "pipeline error: boom", "name": "", "canonical": ""},
]


def test_counts_and_pct():
    md = coverage_markdown("List (4 URLs)", ROWS)
    assert "worked **2 (50%)**" in md
    assert "failed **2 (50%)**" in md


def test_failures_listed_with_reason():
    md = coverage_markdown("L", ROWS)
    assert "https://c.com" in md and "status 403" in md
    assert "https://d.com" in md and "boom" in md


def test_partial_section():
    md = coverage_markdown("L", ROWS)
    assert "PARTIAL (1)" in md and "https://b.com" in md


def test_csv_rows():
    rows = coverage_csv_rows(ROWS)
    assert rows[0] == ["url", "verdict", "reason", "name", "canonical"]
    assert rows[1][1] == "PASS" and len(rows) == 5


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
