

def test_saturday_recap_reports_what_the_load_check_flagged():
    from scripts.weekend_recap import load_qa_lines
    head, flags = load_qa_lines({"flags": ["RSA 2027: evidence page LOST", "x"], "cycle": "2026-10-05", "summary": "s"})
    assert "2 thing(s)" in head and flags[0].startswith("RSA")
    head, flags = load_qa_lines({"flags": [], "cycle": "2026-10-05", "summary": "all consistent"})
    assert "nothing we had proven was lost" in head and flags == []
    head, flags = load_qa_lines(None)
    assert "did not run" in head
