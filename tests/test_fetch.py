"""Offline tests for the resilient-fetch helpers (link classify + block detection)."""
from cfp_monitor.fetch import classify_links, _looks_blocked


def test_internal_vs_external():
    anchors = [
        {"href": "https://www.conf.com/cfp", "text": "Call for Papers"},
        {"href": "https://conf.com/speakers", "text": "Speakers"},
        {"href": "https://sessionize.com/x", "text": "Submit"},
        {"href": "mailto:a@b.com", "text": "email"},
        {"href": "/relative", "text": "rel"},
    ]
    out = classify_links(anchors, "https://conf.com")
    internal = {l["href"] for l in out["internal"]}
    external = {l["href"] for l in out["external"]}
    assert "https://www.conf.com/cfp" in internal          # www normalized to same host
    assert "https://conf.com/speakers" in internal
    assert "https://sessionize.com/x" in external
    # non-http (mailto, relative) dropped everywhere
    allhrefs = internal | external
    assert not any(h.startswith(("mailto", "/")) for h in allhrefs)


def test_dedupe():
    anchors = [{"href": "https://x.com/a", "text": "a"}, {"href": "https://x.com/a", "text": "a2"}]
    out = classify_links(anchors, "https://x.com")
    assert len([l for l in out["internal"] if l["href"] == "https://x.com/a"]) == 1


class _R:
    def __init__(self, ok, md):
        self.success = ok
        self.markdown = md
        self.status_code = 200


def test_is_rich_and_richness():
    from cfp_monitor.fetch import _is_rich, _richness, PageFetch
    thin = PageFetch("u", True, 200, "", "short", {"internal": [{"href": "a"}, {"href": "b"}], "external": []})
    shell = PageFetch("u", True, 200, "", "x" * 5000, {"internal": [], "external": []})  # text but 0 links
    many = PageFetch("u", True, 200, "", "short", {"internal": [{"href": str(i)} for i in range(10)], "external": []})
    assert _is_rich(thin) is False       # < 5 internal links
    assert _is_rich(shell) is False      # lots of text but 0 links -> shell
    assert _is_rich(many) is True        # 10 internal links
    assert _richness(many) > _richness(thin)


def test_looks_blocked():
    assert _looks_blocked(None) is True
    assert _looks_blocked(_R(False, "x" * 500)) is True     # not success
    assert _looks_blocked(_R(True, "short")) is True         # empty shell
    assert _looks_blocked(_R(True, "x" * 500)) is False      # real content


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
