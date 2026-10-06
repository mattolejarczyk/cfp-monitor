"""scripts/control_list.py: the action data is valid, verifying an action moves the register, and the builder cannot verify."""
import copy
import json
import subprocess
import sys
from pathlib import Path

from scripts import control_list as cl

D = cl.load()
FP = json.loads(Path(cl.FP_DATA).read_text(encoding="utf-8"))


def test_the_committed_data_is_valid_and_every_closed_failure_point_exists():
    assert cl.validate(D, FP) == []
    assert {a["wave"] for a in D["actions"]} <= {w["id"] for w in D["waves"]}


def test_verifying_an_action_applies_its_rules_to_the_register_and_needs_evidence():
    d, fp = copy.deepcopy(D), copy.deepcopy(FP)
    d3 = next(i for i in fp["items"] if i["id"] == "D3")
    d3["status"] = "PENDING"                          # the live register already moved D3 to WATCH once ACT-20 was verified: start from a known state
    d3["controls"] = "Overlay, venue-in-city flag."
    before = d3["status"]
    try:
        cl.apply_verify(d, fp, "ACT-20", "   ", "2026-10-06")
        raise AssertionError("verify without evidence must be refused")
    except SystemExit:
        pass
    changes = cl.apply_verify(d, fp, "ACT-20", "reviewed; suite green; sandbox rehearsal clean", "2026-10-06")
    item = next(i for i in fp["items"] if i["id"] == "D3")
    assert item["status"] == "WATCH" and "ACT-20" in item["controls"]
    assert before != "WATCH" and any("D3" in c for c in changes)
    assert next(a for a in d["actions"] if a["id"] == "ACT-20")["state"] == "verified"
    assert cl.validate(d, fp) == []


def test_validation_catches_the_mistakes_that_would_mislead():
    d = copy.deepcopy(D)
    d["actions"][0]["state"] = "verified"
    d["actions"][0]["evidence"] = []
    d["actions"][1]["closes"] = ["Z9"]
    d["actions"][2]["owner"] = "nobody"
    d["actions"].append(copy.deepcopy(d["actions"][3]))
    errs = cl.validate(d, FP)
    assert any("verified without evidence" in e for e in errs) and any("unknown failure point Z9" in e for e in errs)
    assert any("unknown owner" in e for e in errs) and any("duplicate id" in e for e in errs)


def test_the_builder_can_set_every_state_but_verified():
    assert "verified" not in cl.BUILDER_STATES and "review" in cl.BUILDER_STATES
    r = subprocess.run([sys.executable, "scripts/control_list.py", "set", "ACT-20", "--state", "verified"], capture_output=True, text=True, cwd=str(Path(cl.ROOT)))
    assert r.returncode == 1 and "reviewer" in r.stdout


def test_the_page_is_self_contained_carries_the_data_and_both_themes():
    html = cl.build_html(D, FP)
    assert "<title>CFP Control List</title>" in html and "ACT-10" in html and "Needs you" in html
    assert "/*DATA*/null" not in html and "prefers-color-scheme:dark" in html and 'data-theme="dark"' in html
    assert "</script></script>" not in html
