"""A form's POST address is not a page - and banning its host would be the wrong fix.

THE CASE THIS COMES FROM
SecureWorld Seattle 2026 shipped with this in both CFP_SUBMISSION_URL and SUBMISSION URL:

    https://forms.hsforms.com/submissions/v3/public/submit/formsnext/multipart/2221756/f9c6...

That is where a form sends its data. A person clicking it gets an error. Our link checker
recorded it `alive` because the endpoint answered HTTP 405 - it does exist, it just has nothing
on it to read.

WHY NOT SIMPLY BAN hsforms.com
Because the delivery holds EIGHT HubSpot links across FOUR conferences - Climate Week NYC 2026
and Decarb Connect Canada / North America / UK - and every one is a real fillable form on
`share.hsforms.com` carrying the submission details we need. Banning the host deletes four
working submission links to catch one broken one, and the R22 matcher treats subdomains as
matches, so `hsforms.com` would take `share.hsforms.com` with it.

The difference is the PATH, not the host. So is the rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cfp_monitor import rules  # noqa: E402

# Every HubSpot URL actually in the delivery on 2026-09-01. All four are real form pages.
REAL_HUBSPOT_PAGES = [
    "https://share.hsforms.com/1hwCDfSrwQum1gXNUL4l7_A49ffd",
    "https://share.hsforms.com/1jpsiLfnOR1W4MoMaQUL0SA49ffd",
    "https://2f8bnb.share-eu1.hsforms.com/259ObNpA2RHW3DuuC0r4dlQ",
    "https://49ffd.share.hsforms.com/2dMP-kYbBSgCacKlWwJM7Mg",
]
THE_BAD_ONE = ("https://forms.hsforms.com/submissions/v3/public/submit/formsnext/multipart/"
               "2221756/f9c697eb-4f35-4c94-a6fd-0f0abceafced")


def test_the_url_that_shipped_is_caught():
    ok, why = rules.url_is_a_page(THE_BAD_ONE)
    assert not ok
    assert "/submissions/v" in why


def test_the_four_real_hubspot_forms_are_not_touched():
    """The whole reason this is a path rule. If any of these fail, four conferences lose the
    link a speaker uses to submit."""
    for u in REAL_HUBSPOT_PAGES:
        ok, why = rules.url_is_a_page(u)
        assert ok, f"would have deleted a working submission link: {u} ({why})"


def test_hsforms_is_not_on_the_r22_banned_list():
    """R22 is about WHO is speaking. A form platform is not a social network, and putting it on
    that list would both break the four pages above and blur what the rule means."""
    assert not any("hsforms" in h for h in rules.INADMISSIBLE_HOSTS)
    ok, _ = rules.citation_source_admissible("https://share.hsforms.com/abc")
    assert ok


def test_ordinary_submission_pages_are_not_flagged():
    """`/submit` on its own is deliberately NOT a pattern - plenty of real pages end that way.
    A rule that fired on these would be worse than no rule, because people would switch it off."""
    for u in ("https://example.org/call-for-papers/submit",
              "https://example.org/speakers/submit-a-talk",
              "https://sessionize.com/owasp-italy-day-2026-call-for-speakers",
              "https://docs.google.com/forms/d/e/1FAIpQLSe/viewform",
              "https://form.jotform.com/2345678901234",
              "https://owasp.wufoo.com/forms/call-for-papers/",
              "https://www.cvent.com/events/some-conference/speaker-portal"):
        ok, why = rules.url_is_a_page(u)
        assert ok, f"false positive on a real page: {u} ({why})"


def test_other_machine_endpoints():
    for u in ("https://x.example/wp-json/wp/v2/posts",
              "https://x.example/api/v1/sessions",
              "https://x.example/graphql",
              "https://x.example/data/events.json",
              "https://x.example/feed/events.xml",
              "https://x.example/wp-admin/admin-ajax.php?action=x"):
        ok, _ = rules.url_is_a_page(u)
        assert not ok, f"missed an endpoint: {u}"


def test_a_blank_url_is_not_a_violation():
    """2.1 - nothing to judge is not a finding. Otherwise every stub row fails."""
    for u in ("", None, "   "):
        ok, _ = rules.url_is_a_page(u)
        assert ok


def test_it_stays_a_separate_rule_from_r22():
    """Two questions, two answers. A social post IS a page - readable, just not the organiser.
    An API endpoint is NOT a page but is a perfectly respectable host. Neither rule can stand
    in for the other, and the gate reports them separately."""
    social = "https://www.facebook.com/ACTExpo/"
    assert rules.url_is_a_page(social)[0] is True
    assert rules.citation_source_admissible(social)[0] is False

    endpoint = "https://conference.example/api/v1/cfp"
    assert rules.url_is_a_page(endpoint)[0] is False
    assert rules.citation_source_admissible(endpoint)[0] is True


def test_the_gate_reports_it_as_its_own_check():
    src = (ROOT / "scripts" / "accept_delivery.py").read_text(encoding="utf-8")
    assert 'self.add("R22b"' in src
    assert "rules.url_is_a_page" in src
    # It must cover the customer-facing submission URL, not only evidence columns.
    i = src.index('self.add("R22b"')
    block = src[max(0, i - 1400):i]
    assert "SUBMISSION URL" in block and "CFP_SUBMISSION_URL" in block
