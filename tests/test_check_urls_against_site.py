"""A URL checker that trusts status codes is not a URL checker.

This tool exists because on 2026-08-31 five DIFFERENT guessed call-for-speakers URLs across
three SecureWorld hosts all returned HTTP 200 while saying "page not found" in the body. Every
one had the shape `sitewalk.FALLBACK_PATHS` guesses. With no CFP page reachable, the deadline
was taken from an events LISTING, and all eight SecureWorld rows stored a conference date in
SUBMISSION DEADLINE.

The site's own sitemap had the real page - `www.secureworld.io/speaker-submissions`, plural,
no trailing slash, on `www` rather than `events`. Asking the site for its index found in one
request what five guesses missed.

No network here. These test the judgement, not the fetching.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "_cu", ROOT / "scripts" / "check_urls_against_site.py")
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)


def test_a_200_that_says_page_not_found_is_not_ok():
    """The exact bodies we got back. A status-code check called all of these live."""
    for body in ("Oops! That page can't be found. It looks like nothing was found at this "
                 "location. Maybe try a search?",
                 "404 Not Found - the page you requested does not exist on this server, "
                 "please use the navigation above to find what you were looking for."):
        assert cu.looks_soft_404(body), f"missed a soft 404: {body[:40]!r}"


def test_a_consent_shell_is_not_a_page():
    """`secureworld.io/speaker-submission-form` returned a cookie banner and a nav bar. There is
    no call for papers on it, and nothing that reads only the status code can tell."""
    shell = ("This website stores cookies on your computer. Accept Decline "
             "SecureWorld St. Louis is This Week!")
    assert cu.looks_soft_404(shell)


def test_a_real_page_passes():
    body = ("Call for Speakers. We are now accepting session proposals for the 2027 "
            "conference. The submission deadline is 9 September 2026 at 23:59 UTC. "
            "Proposals are reviewed by the programme committee and speakers are notified "
            "in October. Please include a title, an abstract of up to 300 words, and a "
            "short biography with each submission you send to the committee for review.")
    assert cu.looks_soft_404(body) == ""


def test_headshots_are_not_call_for_papers_pages():
    """`sitewalk.relevance` scores on the path, so `/hubfs/speakers/Aaron-Jentzen.jpg` looked
    call-for-speakers-like. `rank_links` never sees that because it applies NOT_A_PAGE first;
    a sitemap arrives unfiltered, so this must apply it too - otherwise the answer to "does
    this site publish a call page" is a list of headshots. That was the first output."""
    urls = ["https://x.example/hubfs/speakers/Aaron-Jentzen.jpg",
            "https://x.example/hubfs/call-center-2275745_640.jpg",
            "https://x.example/call-for-papers"]
    got = [u for _s, u in cu.cfp_like(urls)]
    assert got == ["https://x.example/call-for-papers"]


def test_cfp_like_does_not_repeat_a_url():
    """Sitemap and navigation overlap, and a page listed twice is not twice as good."""
    u = "https://x.example/call-for-papers"
    assert len(cu.cfp_like([u, u, u])) == 1


def test_origin_of_ignores_the_path():
    assert cu.origin_of("https://www.secureworld.io/events") == "https://www.secureworld.io"
    assert cu.origin_of("not a url") == ""


def test_the_five_guesses_are_the_shape_sitewalk_would_invent():
    """Not a test of this script so much as of why it was needed: the URLs that 404ed are the
    ones the fallback generates. When a site exposes no usable links we guess, and a guess that
    happens to return 200 is indistinguishable from a find without asking the site's index."""
    from src.cfp_monitor import sitewalk
    guessed = set(sitewalk.fallback_urls("https://www.secureworld.io/events"))
    assert "https://www.secureworld.io/call-for-speakers/" in guessed
    assert "https://www.secureworld.io/speakers/" in guessed


def test_robots_is_asked_before_paths_are_guessed():
    """`events.secureworld.io/robots.txt` names two sitemaps totalling 11,237 URLs. Asking is
    one request and it is authoritative; the conventional paths are only for sites that name
    none."""
    from src.cfp_monitor import sitewalk
    robots = ("User-agent: *\nDisallow: /wp-admin/\n"
              "Sitemap: https://events.secureworld.io/sitemap.xml\n"
              "Sitemap: /news-sitemap.xml\n")
    got = sitewalk.sitemaps_from_robots(robots, "https://events.secureworld.io/details/x/")
    assert got == ["https://events.secureworld.io/sitemap.xml",
                   "https://events.secureworld.io/news-sitemap.xml"], "relative Sitemap: too"
    assert sitewalk.sitemaps_from_robots("User-agent: *\nDisallow:", "https://x.example") == []


def test_a_sitemap_index_is_told_from_a_sitemap():
    """An index points at more sitemaps. Treating its <loc>s as pages yields a list of XML
    files and no site content at all."""
    from src.cfp_monitor import sitewalk
    ns = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    idx = f'<?xml version="1.0"?><sitemapindex {ns}><sitemap>' \
          f'<loc>https://x.example/sm1.xml</loc></sitemap></sitemapindex>'
    page = f'<?xml version="1.0"?><urlset {ns}><url>' \
           f'<loc>https://x.example/call-for-papers</loc></url></urlset>'
    locs, is_index = sitewalk.parse_sitemap(idx)
    assert is_index and locs == ["https://x.example/sm1.xml"]
    locs, is_index = sitewalk.parse_sitemap(page)
    assert not is_index and locs == ["https://x.example/call-for-papers"]


def test_a_sitemap_that_is_not_xml_is_not_a_crash():
    """A guessed sitemap path routinely returns the site's HTML 404 page."""
    from src.cfp_monitor import sitewalk
    for junk in ("<!doctype html><html><body>Not found</body></html>", "", "   ", "not xml"):
        assert sitewalk.parse_sitemap(junk) == ([], False)


def test_it_writes_nothing():
    """A URL existing is not proof it carries the deadline we claim. Retargeting is a separate,
    evidenced step - this tool must not quietly take it."""
    src = (ROOT / "scripts" / "check_urls_against_site.py").read_text(encoding="utf-8")
    for bad in ("to_csv", "DictWriter", "shutil.copy"):
        assert bad not in src, f"{bad} - this tool is read-only"
