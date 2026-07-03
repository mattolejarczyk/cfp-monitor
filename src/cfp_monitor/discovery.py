"""Per-page target discovery: links, buttons/CTAs, and forms (feat 3, 4, 9).

These helpers turn a crawled page's HTML into candidate crawl targets. They're used
by the score-driven explorer (crawler.py) on EVERY page, not just the homepage — the
start URL is only the entry point.
"""
from __future__ import annotations

from urllib.parse import urljoin

from .keywords import SUBMISSION_PLATFORMS
from .scoring import detect_submission_platform, score_link, normalize_url


# Strong submission signals for classifying a <form> (deliberately excludes bare
# "enter"/"apply" so newsletter/search forms don't get mistaken for submissions).
_SUBMISSION_TOKENS = (
    "submit", "submission", "proposal", "propose", "abstract", "cfp", "call for",
    "call-for", "speaker", "nominat", "best-of-show", "best of show", "awards entry",
    "award entry", "call for entries", "enter the awards", "submit an entry",
    "paper", "poster", "speaking",
)


def _is_submission_form(action_url: str, context: str) -> bool:
    low = f"{action_url} {context}".lower()
    return any(t in low for t in _SUBMISSION_TOKENS)


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None
    try:
        return BeautifulSoup(html or "", "html.parser")
    except Exception:
        return None


def extract_clickables(html: str, base_url: str) -> list[dict]:
    """Anchors + nav items + role=button / <button> elements, as {href, text}.
    Buttons/CTAs are first-class here — many lead straight to the opportunity."""
    soup = _soup(html)
    if soup is None:
        return []
    out: list[dict] = []
    for el in soup.select("a[href], [role=button], button"):
        text = el.get_text(" ", strip=True)
        href = el.get("href") or el.get("data-href") or el.get("data-url")
        if href:
            out.append({"href": urljoin(base_url, href), "text": text})
    return out


def detect_forms(html: str, base_url: str) -> list[dict]:
    """Find live submission/entry forms on the page — <form action=...>, embedded
    platform <iframe>s, and links to known submission platforms. Returns
    [{url, platform, context}]. A form is strong opportunity evidence (feat 3)."""
    soup = _soup(html)
    if soup is None:
        return []
    forms: list[dict] = []
    seen: set[str] = set()   # dedupe by normalized URL (http/https + trailing slash)

    def add(url: str, context: str):
        if not url:
            return
        full = urljoin(base_url, url)
        key = normalize_url(full)
        if key in seen:
            return
        seen.add(key)
        forms.append(
            {"url": full, "platform": detect_submission_platform(full) or "on-page form", "context": (context or "")[:160]}
        )

    # 1. <form> elements — keep only submission-relevant ones (token match on the
    #    action path + surrounding text) so search/newsletter/brochure forms don't pollute.
    for f in soup.select("form"):
        action = (f.get("action") or "").strip()
        if not action:
            continue
        full = urljoin(base_url, action)
        context = f.get_text(" ", strip=True)[:160]
        if detect_submission_platform(full) or _is_submission_form(full, context):
            add(full, context)
    # 2. embedded platform iframes (HubSpot, Jotform, Typeform, Google Forms, Sessionize…)
    for fr in soup.select("iframe[src]"):
        src = fr.get("src") or ""
        if detect_submission_platform(src):
            add(src, "embedded form")
    # 3. links pointing at a known submission platform
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if detect_submission_platform(href):
            add(href, a.get_text(" ", strip=True))
    return forms[:12]
