"""Offline tests for the coverage report formatter."""
from cfp_monitor.coverage import coverage_markdown, coverage_csv_rows, summarize
from cfp_monitor.models import ConferenceResult, Fact

ROWS = [
    {"url": "https://a.com", "verdict": "PASS", "reason": "core facts", "name": "A Conf",
     "canonical": "https://a.com", "path": "crawl4ai", "bypass": "", "hop": False},
    {"url": "https://b.com", "verdict": "PARTIAL", "reason": "thin content", "name": "",
     "canonical": "https://b.com", "path": "playwright-fallback", "bypass": "playwright-fallback", "hop": False},
    {"url": "https://c.com", "verdict": "BLOCKED", "reason": "anti-bot / refused status 403", "name": "",
     "canonical": "", "path": "unresolved", "bypass": "cdp", "hop": False},
    {"url": "https://d.com", "verdict": "ERROR", "reason": "pipeline error: boom", "name": "",
     "canonical": "", "path": "unresolved", "bypass": "", "hop": False},
]


def test_counts_and_pct():
    md = coverage_markdown("List (4 URLs)", ROWS)
    assert "worked **2 (50%)**" in md
    assert "failed **2 (50%)**" in md


def test_failures_listed_with_bypass_and_reason():
    md = coverage_markdown("L", ROWS)
    assert "https://c.com" in md and "status 403" in md and "Signed-in browser" in md
    assert "https://d.com" in md and "boom" in md


def test_path_matrix_uses_plain_terms():
    md = coverage_markdown("L", ROWS)
    assert "By resolution path" in md
    assert "Core crawl (first pass)" in md
    assert "Browser control (rendered)" in md
    # internal tool names must NOT leak into the customer-facing report
    assert "crawl4ai" not in md and "playwright" not in md


def test_partial_section():
    md = coverage_markdown("L", ROWS)
    assert "PARTIAL (1)" in md and "https://b.com" in md


def test_csv_rows():
    rows = coverage_csv_rows(ROWS)
    assert rows[0] == ["url", "verdict", "path", "bypass", "hop", "reason", "name", "canonical"]
    assert rows[1][1] == "PASS" and len(rows) == 5


def test_summarize_reads_path_and_hop():
    r = ConferenceResult(start_url="https://x.com")
    r.name = Fact(value="X Conf")
    r.resolution_path = "cdp"
    r.aggregator_hop = True
    r.pages_crawled = 3
    r.trace = [{"action": "fallback", "reason": "cdp render"}]
    row = summarize([r])[0]
    assert row["path"] == "cdp"
    assert row["hop"] is True
    assert row["bypass"] == "cdp"
    assert row["verdict"] == "PASS"


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
