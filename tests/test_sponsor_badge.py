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
    # the open row: the old claim "speaking requires sponsorship" is made ONLY for a confirmed row; an unconfirmed one says what we actually know (2026-10-19)
    assert "r.sponlabel?'speaking at this event requires sponsorship.'" in src
    assert "sponsorship and exhibitor information from our research" in src
    assert "We have not yet read a sentence" not in src


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


# ------------------------------------------------------------------ how to speak (scripts/speaking_route.py)
def route_row(route, **kw):
    base = {"route": route, "call_quote": "Call for Speakers", "call_url": "https://e.example/cfp", "paid_quote": "", "paid_url": "", "must_quote": "", "must_url": ""}
    base.update(kw)
    return base


def test_a_verified_must_sponsor_route_gives_the_badge_but_never_against_an_upstream_no():
    for v in ("Yes", "Unknown", "", None):
        assert brp.sponsor_badge_label(v, "", route="MUST_SPONSOR") == "Sponsor required"
    assert brp.sponsor_badge_label("No", "", route="MUST_SPONSOR") == ""
    for other in ("OPEN_CALL", "OPEN_CALL_AND_PAID_SLOTS", "PAID_SLOTS_NO_CALL_SEEN", "INVITE_ONLY", ""):
        assert brp.sponsor_badge_label("Yes", "", route=other) == ""             # paid slots are not a requirement


def test_built_rows_carry_the_route_its_quotes_and_pages():
    out = brp.build([row(**{"SPONSOR_REQUIRED": "Yes"}), row(**{"EVENT_ID": "2027-other-boston", "SPONSOR_REQUIRED": "Yes"}), row(**{"EVENT_ID": "2027-third-denver"})],
                    routes={"2027-thing-austin": route_row("OPEN_CALL"), "2027-other-boston": route_row("UNCLEAR")})
    by = {r["n"] if False else i: r for i, r in enumerate(out)}
    a, b, c = out[0], out[1], out[2]
    assert a["route"] == "OPEN_CALL" and a["routecq"] == "Call for Speakers" and a["routecu"] == "https://e.example/cfp" and a["sponlabel"] == ""
    assert b["route"] == "" and b["routecq"] == ""                                # UNCLEAR is never shown
    assert c["route"] == ""                                                       # never judged


def test_the_page_says_how_to_speak_and_no_longer_claims_a_requirement_it_has_not_proven():
    src = (ROOT / "scripts" / "build_review_page.py").read_text(encoding="utf-8")
    assert "<h4>How to speak</h4>" in src and "ROUTE_TEXT[r.route]" in src and "const ROUTE_TEXT = __ROUTE_TEXT__;" in src
    assert "'__ROUTE_TEXT__', json.dumps(ROUTE_LABELS)" in src.replace('"', "'") or "__ROUTE_TEXT__" in src
    for k in ("OPEN_CALL", "OPEN_CALL_AND_PAID_SLOTS", "PAID_SLOTS_NO_CALL_SEEN", "MUST_SPONSOR", "INVITE_ONLY"):
        assert k in brp.ROUTE_LABELS and brp.ROUTE_LABELS[k].endswith(".")
    assert "UNCLEAR" not in brp.ROUTE_LABELS
    assert "requires sponsorship" not in brp.ROUTE_LABELS["PAID_SLOTS_NO_CALL_SEEN"]
