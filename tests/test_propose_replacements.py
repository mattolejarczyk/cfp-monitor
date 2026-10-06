"""scripts/propose_replacements.py (ACT-24): digest parsing, scope, and what counts as a proposal. Fixture-only: no network, no model."""
from scripts import propose_replacements as P

DIGEST = """# Weekly verification - 2026-10-04

## NEW dead links since the last run (2)

- **BSides Las Vegas 2026 (BSidesLV)** - https://bsideslv.org/participate/cfp
- **CES 2027 (Consumer Electronics Show - Smart Energy & Clean Tech)** - https://www.ces.tech/speaking-at-ces/

## Database watch items (1)

- **edition matches the name year - 5 row(s)** - watch: run fix_edition.py to derive from date

## Standing backlog - already dead before this run (2)

- **ISE 2027 (Integrated Systems Europe)** - https://www.iseurope.org/ise-content-programme
- **SecureWorld Seattle 2026** - https://www.secureworld.io/events/seattle-2026

## No longer evidenced - citation cleared (1)

- Argus Biofuels Europe Conference & Exhibition 2026
"""


def test_the_digest_gives_new_and_backlog_links_and_nothing_else():
    links = P.parse_digest(DIGEST)
    assert [(l["section"], l["event"]) for l in links] == [("new", "BSides Las Vegas 2026 (BSidesLV)"), ("new", "CES 2027 (Consumer Electronics Show - Smart Energy & Clean Tech)"),
                                                           ("backlog", "ISE 2027 (Integrated Systems Europe)"), ("backlog", "SecureWorld Seattle 2026")]
    assert links[0]["url"] == "https://bsideslv.org/participate/cfp"


def test_the_real_latest_digest_shape_is_parseable_if_present():
    import glob
    import os
    files = sorted(glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "runs_out", "weekly_verify_*.md")))
    if not files:
        return
    links = P.parse_digest(open(files[-1], encoding="utf-8").read())
    assert all(l["url"].startswith("http") and l["event"] and l["section"] in ("new", "backlog") for l in links)


def test_link_kind_call_or_info():
    assert P.link_kind("https://bsideslv.org/participate/cfp") == "call"
    assert P.link_kind("https://www.ces.tech/speaking-at-ces/") == "call"
    assert P.link_kind("https://www.secureworld.io/events/seattle-2026") == "info"
    assert P.link_kind("https://sessionize.com/global-appsec-us-2026/") == "info"


ROWS = [{"name": "ISE 2027 (Integrated Systems Europe)", "start_date": "2027-02-02", "edition": "2027"},
        {"name": "SecureWorld Seattle 2026", "start_date": "2026-08-01", "edition": "2026"},
        {"name": "Old Show", "start_date": "", "edition": "2025"}]


def test_locate_is_exact_or_very_close_never_a_guess():
    assert P.locate("ise 2027 (integrated systems europe)", ROWS)["name"].startswith("ISE")
    assert P.locate("Totally Different Congress", ROWS) is None


def test_a_past_edition_is_not_chased():
    assert P.past_edition(ROWS[1], "2026-10-05") and P.past_edition(ROWS[2], "2026-10-05") and not P.past_edition(ROWS[0], "2026-10-05")


def test_the_start_address_is_never_the_dead_link_and_never_an_aggregator():
    row = {"main_info_url": "https://x.example/dead", "url": "https://x.example/", "submission_url": "https://sessionize.com/x", "deadline_evidence_url": ""}
    assert P.home_candidates(row, {"https://x.example/dead"}) == ["https://x.example/"]
    only_dead = {"main_info_url": "https://y.example/dead", "url": "", "submission_url": "", "deadline_evidence_url": ""}
    assert P.home_candidates(only_dead, {"https://y.example/dead"}) == ["https://y.example/"]                      # the site root of the dead address
    agg = {"main_info_url": "", "url": "", "submission_url": "", "deadline_evidence_url": ""}
    assert P.home_candidates(agg, {"https://redcanary.com/blog/cfp-tracker-august-2025/"}) == []                   # a tracker page is not the event's site


def test_names_event_needs_the_events_distinctive_words_in_one_sentence():
    text = "Welcome. SecureWorld Seattle brings the community together on 5 November 2026. Cookies are used."
    assert "SecureWorld Seattle" in P.names_event(text, "SecureWorld Seattle 2026")
    assert P.names_event("A page about gardening in Seattle.", "SecureWorld Seattle 2026") == ""


REC = {"pages": [{"rank": -1, "url": "https://x.example/", "chars": 4000, "accepted": "", "quote": ""},
                 {"rank": 1, "url": "https://x.example/call-for-speakers", "chars": 3000, "accepted": "2026-12-01", "quote": "Submissions close on December 1, 2026."}],
       "pick": {"pick": "2026-12-01", "why": "main-page: https://x.example/call-for-speakers"}}
CACHE = {"https://x.example/": "Welcome to Example Security Summit 2027, the annual gathering of defenders in Oslo.",
         "https://x.example/call-for-speakers": "Example Security Summit 2027 call for speakers. Submissions close on December 1, 2026. Tell us about your talk."}


def test_a_call_link_gets_a_proposal_only_with_a_proven_deadline():
    r = P.propose_for_link({"url": "https://x.example/cfp"}, REC, CACHE, "Example Security Summit 2027", "2026-10-05")
    assert r["status"] == "PROPOSED" and r["proposed_url"].endswith("/call-for-speakers") and r["deadline"] == "2026-12-01" and "December 1" in r["quote"]
    no_pick = {"pages": REC["pages"], "pick": {"pick": ""}}
    lead = P.propose_for_link({"url": "https://x.example/cfp"}, no_pick, CACHE, "Example Security Summit 2027", "2026-10-05")
    assert lead["status"] == "LEAD" and lead["deadline"] == "" and lead["proposed_url"].endswith("/call-for-speakers")
    nothing = P.propose_for_link({"url": "https://x.example/cfp"}, {"pages": [REC["pages"][0]], "pick": {"pick": ""}}, CACHE, "Example Security Summit 2027", "2026-10-05")
    assert nothing["status"] == "NONE"


def test_an_event_link_gets_a_proposal_only_when_the_live_page_names_the_event():
    ok = P.propose_for_link({"url": "https://x.example/about-us"}, REC, CACHE, "Example Security Summit 2027", "2026-10-05")
    assert ok["status"] == "PROPOSED" and ok["proposed_url"] == "https://x.example/" and "Oslo" in ok["quote"]
    other = P.propose_for_link({"url": "https://x.example/about-us"}, REC, {"https://x.example/": "A page about something else entirely, long enough to read."}, "Example Security Summit 2027", "2026-10-05")
    assert other["status"] == "NONE"


def test_an_unreadable_site_is_reported_as_such_and_never_proposed():
    assert P.propose_for_link({"url": "https://x.example/cfp"}, {"skipped": "anti-bot host"}, {}, "E", "2026-10-05")["status"] == "UNREADABLE"
    assert P.propose_for_link({"url": "https://x.example/cfp"}, {"pages": [{"rank": -1, "url": "u", "chars": 10}]}, {}, "E", "2026-10-05")["status"] == "UNREADABLE"


def test_the_script_is_read_only_and_capped():
    src = open(P.__file__, encoding="utf-8").read()
    assert "mode=ro" in src and "default=0.30" in src and "default=150" in src
    for bad in ("UPDATE ", "INSERT ", "DELETE ", "smtplib", "maybe_send_email"):
        assert bad not in src


# ----- ACT-42: a date on a shared page is a LEAD, not a proposal; wrong-kind pages are dropped -----
SANS_PAGE = ("Speak at a SANS Summit. Call for Presentations. SANS Cyber Threat Intelligence Summit and OSINT Summit, Alexandria, VA, February 2027. "
             "Submit your proposal for the CTI Summit and the OSINT Summit by October 19, 2026. SANS Security Leadership Summit and ICS Summit call for papers open in the new year.")
SANS_REC = {"pages": [{"rank": -1, "url": "https://www.sans.org/", "chars": 4000, "accepted": "", "quote": ""},
                      {"rank": 1, "url": "https://www.sans.org/cyber-security-summit/speak-at-a-summit", "chars": 3000, "accepted": "2026-10-19",
                       "quote": "Submit your proposal for the CTI Summit and the OSINT Summit by October 19, 2026."}],
            "pick": {"pick": "2026-10-19", "why": "main-page: speak-at-a-summit"}}


def test_the_sans_cdi_false_proposal_is_now_a_lead_not_a_proposal():
    """2026-10-05: SANS Cyber Defense Initiative 2026 was 'proposed' the 19 October deadline of the CTI and OSINT summits, from the shared speak-at-a-summit page."""
    cache = {"https://www.sans.org/cyber-security-summit/speak-at-a-summit": SANS_PAGE}
    r = P.propose_for_link({"url": "https://www.sans.org/call-for-presentations/"}, SANS_REC, cache, "SANS Cyber Defense Initiative 2026 (CDI 2026)", "2026-10-06")
    assert r["status"] == "LEAD" and r["deadline"] == "" and "nothing next to it names this event" in r["note"]
    # the same page IS a proposal for the event it is about
    ok = P.propose_for_link({"url": "https://www.sans.org/call-for-presentations/"}, SANS_REC, cache, "SANS Cyber Threat Intelligence Summit and OSINT Summit 2027", "2026-10-06")
    assert ok["status"] == "PROPOSED" and ok["deadline"] == "2026-10-19"


def test_an_awards_or_degree_programme_page_is_not_a_call_or_event_page_for_a_conference():
    awards = {"pages": [{"rank": -1, "url": "https://x.example/", "chars": 4000, "accepted": "", "quote": ""},
                        {"rank": 1, "url": "https://x.example/awards/entries", "chars": 3000, "accepted": "2026-12-01", "quote": "Example Security Summit entries close December 1, 2026."}],
              "pick": {"pick": "2026-12-01", "why": "x"}}
    r = P.propose_for_link({"url": "https://x.example/cfp"}, awards, {"https://x.example/awards/entries": "Example Security Summit entries close December 1, 2026."}, "Example Security Summit 2027", "2026-10-06")
    assert r["status"] == "NONE" and "awards" in r["note"]
    assert P.wrong_kind("https://uni.example/study/phd-programme/", "Example Summit 2027") == "phd"
    assert P.wrong_kind("https://x.example/awards/", "Example Awards 2027") == ""            # an event that IS an awards programme keeps its awards page
    info = {"pages": [{"rank": 1, "url": "https://uni.example/phd/", "chars": 4000, "accepted": "", "quote": ""}], "pick": {}}
    assert P.propose_for_link({"url": "https://x.example/about"}, info, {"https://uni.example/phd/": "Example Summit 2027 is held every year at the university in Oslo."}, "Example Summit 2027", "2026-10-06")["status"] == "NONE"
