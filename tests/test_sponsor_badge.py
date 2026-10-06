"""R-002 (ACT-62): the customer-page sponsorship badge. Yes + quote = 'Sponsor required'; Yes + no quote = 'Sponsor required (unconfirmed)'; not a Yes = no badge."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("brp", ROOT / "scripts" / "build_review_page.py")
brp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brp)


def row(**kw):
    base = {k: "" for k in brp.FIELDS}
    base["EVENT_ID"] = "2027-thing-austin"
    base.update(kw)
    return base


def test_label_function():
    q = "Speaker slots require a Gold sponsorship."
    assert brp.sponsor_badge_label("Yes", q) == "Sponsor required"
    assert brp.sponsor_badge_label("yes ", q) == "Sponsor required"
    assert brp.sponsor_badge_label("Yes", "") == "Sponsor required (unconfirmed)"
    assert brp.sponsor_badge_label("Yes", "   ") == "Sponsor required (unconfirmed)"
    assert brp.sponsor_badge_label("Yes", None) == "Sponsor required (unconfirmed)"
    for v in ("No", "Unknown", "", None):
        assert brp.sponsor_badge_label(v, "a quote") == ""


def test_built_rows_carry_the_label_and_the_template_uses_it_for_the_badge():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": "Sponsorship is required to speak."}),
                     row(**{"EVENT_ID": "2027-other-boston", "SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": ""})])
    labels = sorted(r["sponlabel"] for r in out)
    assert labels == ["Sponsor required", "Sponsor required (unconfirmed)"]
    assert all(r["spon"] for r in out)
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "${esc(r.sponlabel)}" in src                                  # the badge text comes from the label, no longer a fixed string
    assert ">Sponsor required${" not in src
    # the detail text is unchanged
    assert "We have not yet read a sentence on their page confirming this." in src
    assert "speaking at this event requires sponsorship." in src


def test_a_not_yes_row_has_no_label():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "No", "SPONSOR_QUOTE": "x"})])
    assert out[0]["sponlabel"] == "" and out[0]["spon"] is False
