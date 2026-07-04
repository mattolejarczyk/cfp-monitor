"""Offline tests for robust button/clickable URL extraction (masked URLs)."""
from cfp_monitor.discovery import extract_clickables

BASE = "https://conf.example.com/"


def _hrefs(html):
    return {c["href"] for c in extract_clickables(html, BASE)}


def test_plain_anchor():
    assert "https://conf.example.com/cfp" in _hrefs('<a href="/cfp">Call for Papers</a>')


def test_data_href_button():
    assert "https://conf.example.com/speak" in _hrefs('<button data-href="/speak">Speak</button>')


def test_onclick_location():
    assert "https://conf.example.com/submit" in _hrefs("<button onclick=\"location.href='/submit'\">Submit</button>")


def test_onclick_window_open():
    assert "https://conf.example.com/abstract" in _hrefs("<div role=button onclick=\"window.open('/abstract')\">A</div>")


def test_formaction():
    assert "https://conf.example.com/apply" in _hrefs('<button formaction="/apply">Apply</button>')


def test_wrapping_anchor():
    assert "https://conf.example.com/become-a-speaker" in _hrefs('<a href="/become-a-speaker"><button>Become a Speaker</button></a>')


def test_input_submit_formaction():
    cs = extract_clickables('<input type="submit" formaction="/enter" value="Enter Awards">', BASE)
    assert any(c["href"].endswith("/enter") for c in cs)


def test_skips_non_navigation():
    html = '<a href="javascript:void(0)">x</a><a href="#top">y</a><a href="mailto:a@b.com">z</a>'
    assert _hrefs(html) == set()


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
