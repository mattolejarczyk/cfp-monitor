"""The customer-page sponsorship badge. CHANGED 2026-10-19 (operator): Yes + a verbatim quote, or Yes + the customer's own sheet saying it is required = 'Sponsor required'; an unconfirmed Yes shows NO badge; not a Yes = no badge."""
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
    assert brp.sponsor_badge_label("Yes", "") == ""                       # unconfirmed: no badge at all
    assert brp.sponsor_badge_label("Yes", "   ") == ""
    assert brp.sponsor_badge_label("Yes", None) == ""
    assert brp.sponsor_badge_label("Yes", "", customer_confirmed=True) == "Sponsor required"
    assert brp.sponsor_badge_label("No", "", customer_confirmed=True) == ""   # the customer cannot make a No into a Yes
    for v in ("No", "Unknown", "", None):
        assert brp.sponsor_badge_label(v, "a quote") == ""


def test_built_rows_carry_the_label_and_the_template_uses_it_for_the_badge():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": "Sponsorship is required to speak."}),
                     row(**{"EVENT_ID": "2027-other-boston", "SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": ""})])
    labels = sorted(r["sponlabel"] for r in out)
    assert labels == ["", "Sponsor required"]
    assert all(r["spon"] for r in out)                                   # the detail text still opens for an unconfirmed Yes
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "${esc(r.sponlabel)}" in src                                  # the badge text comes from the label, no longer a fixed string
    assert "(r.spon&&r.sponlabel)?" in src                               # an empty label draws no badge at all (no empty pill)
    assert ">Sponsor required${" not in src
    # the detail text is unchanged
    assert "We have not yet read a sentence on their page confirming this." in src
    assert "speaking at this event requires sponsorship." in src


def test_a_not_yes_row_has_no_label():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "No", "SPONSOR_QUOTE": "x"})])
    assert out[0]["sponlabel"] == "" and out[0]["spon"] is False


def test_customer_sheet_confirmation_gives_the_badge_without_a_quote():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": ""}),
                     row(**{"EVENT_ID": "2027-other-boston", "SPONSOR_REQUIRED": "Yes", "SPONSOR_QUOTE": ""})],
                    sponsor_cust={"2027-other-boston"})
    labels = [r["sponlabel"] for r in out]
    assert sorted(labels) == ["", "Sponsor required"]


def test_customer_says_sponsor_required_reads_their_own_words_and_ignores_negations():
    yes = ["Sponsorship are required for speaking.", "Must be Exhibitor/ Sponsor", "Sponsorship Required",
           "Accepted, but requires a sponsorship for 15 minute presentation - Sponsorship minimum is $12,500"]
    no = ["Blinded reviews completely disconnected from sponsorship.", "No corporate sponsors on badge.", "Sponsorship not required",
          "sponsorship is not required to speak", "Arnica is a Diamond Exhibitor", "sponsorship is optional", ""]
    for t in yes:
        assert brp.customer_says_sponsor_required({"notes": t}), t
    for t in no:
        assert not brp.customer_says_sponsor_required({"notes": t}), t
    assert brp.customer_says_sponsor_required({"their_deadline": "Sponsorship Required"})
    # contact details and overview text are not evidence
    assert not brp.customer_says_sponsor_required({"coordinator_contact": "Sponsorship required enquiries: x", "overview": "sponsorship is required"})
