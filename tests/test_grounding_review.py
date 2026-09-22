"""The grounding trail's composed-URL signal must become a decision, not a number.

A row that searched but cited a host it never searched is surfaced for a person with a concrete
action (verify, then withdraw if unsupported - never self-rewrite). A row that in-sources its
citation is left alone; a stub is routed to --redo-stubs.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import grounding_review as gr  # noqa: E402


def _outcome(row, opp="Awards", searched=True, stub=False, cite="", in_sources=None, hosts=None):
    return {"kind": "outcome", "pass": "research", "row": row, "opportunity_type": opp,
            "searched": searched, "stub": stub, "citation_host": cite,
            "citation_host_in_sources": in_sources, "source_hosts": hosts or []}


ASTORS = _outcome("ASTORS Homeland Security Awards", cite="americansecuritytoday.com",
                  in_sources=False, hosts=["cyemptive.com", "asterawards.com", "tradefairdates.com"])
BLACKHAT = _outcome("Black Hat Startup Spotlight", cite="blackhat.com", in_sources=True,
                    hosts=["blackhat.com", "businesswire.com"])
STUB = _outcome("Channel Partners / MSP 501 Awards", searched=False, stub=True)


def test_only_the_composed_row_is_flagged():
    r = gr.build_review([ASTORS, BLACKHAT, STUB])
    assert [o["row"] for o in r["composed"]] == ["ASTORS Homeland Security Awards"]
    assert [o["row"] for o in r["no_search"]] == ["Channel Partners / MSP 501 Awards"]


def test_report_gives_a_concrete_action_for_a_composed_citation():
    text = gr.render(gr.build_review([ASTORS]), "run")
    assert "ASTORS Homeland Security Awards" in text
    assert "americansecuritytoday.com" in text
    assert "withdraw the citation" in text and "never invent" in text
    # awards rows point at the awards verifier
    assert "check_award_deadlines.py" in text


def test_conference_row_points_at_the_conference_verifier():
    conf = _outcome("Some Conf", opp="Speaking", cite="redcanary.com", in_sources=False,
                    hosts=["example.com"])
    text = gr.render(gr.build_review([conf]), "run")
    assert "audit_evidence.py" in text


def test_stub_row_is_routed_to_redo_stubs():
    text = gr.render(gr.build_review([STUB]), "run")
    assert "NO SEARCH RAN" in text and "--redo-stubs" in text


def test_a_clean_run_says_so():
    text = gr.render(gr.build_review([BLACKHAT]), "run")
    assert "clean" in text
    assert "CITATION ON A HOST" not in text


def test_review_file_end_to_end(tmp_path):
    p = tmp_path / "Awards_x.grounding.jsonl"
    lines = [json.dumps({"kind": "attempt", "row": "ASTORS Homeland Security Awards"}),
             json.dumps(ASTORS), json.dumps(BLACKHAT), json.dumps(STUB)]
    p.write_text("\n".join(lines), encoding="utf-8")
    text = gr.review_file(p)
    assert "ASTORS Homeland Security Awards" in text
    assert "1 citation(s) to check, 1 row(s) that ran no search" in text
