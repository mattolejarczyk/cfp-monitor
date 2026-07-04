"""Per-page target discovery: links, buttons/CTAs, and forms (feat 3, 4, 9).

These helpers turn a crawled page's HTML into candidate crawl targets. They're used
by the score-driven explorer (crawler.py) on EVERY page, not just the homepage — the
start URL is only the entry point.
"""
from __future__ import annotations

import re
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


# URL hidden inside an onclick handler, e.g. onclick="location.href='/cfp'".
_ONCLICK_URL = re.compile(
    r"""(?:location\.href|window\.location(?:\.href)?|location\.assign|window\.open)\s*[=(]\s*['"]([^'"]+)['"]""",
    re.I,
)
# data-* attributes commonly used to carry a navigation target on a button.
_DATA_URL_ATTRS = ("data-href", "data-url", "data-link", "data-target-url", "data-goto", "data-navigate")


def _button_url(el) -> str | None:
    """Best-effort real URL behind a clickable, including URLs MASKED by buttons —
    onclick JS navigation, formaction, data-* attrs, or a wrapping <a>."""
    for attr in ("href",) + _DATA_URL_ATTRS:
        v = el.get(attr)
        if v:
            return v
    if el.get("formaction"):
        return el.get("formaction")
    m = _ONCLICK_URL.search(el.get("onclick") or "")
    if m:
        return m.group(1)
    a = el.find_parent("a", href=True)
    if a:
        return a.get("href")
    return None


def extract_clickables(html: str, base_url: str) -> list[dict]:
    """Anchors + buttons/CTAs as {href, text}. Buttons are first-class and often MASK
    the real URL in onclick / formaction / data-* attributes — we dig those out so
    JS-masked opportunity links aren't lost. (Only pure SPA-router buttons with no URL
    anywhere escape us — those would need an actual click in the browser.)"""
    soup = _soup(html)
    if soup is None:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for el in soup.select("a[href], [role=button], button, [onclick], input[type=submit], input[type=button]"):
        raw = _button_url(el)
        if not raw:
            continue
        raw = raw.strip()
        low = raw.lower()
        if not raw or low.startswith(("javascript:", "#", "mailto:", "tel:", "data:")):
            continue
        full = urljoin(base_url, raw)
        if full in seen:
            continue
        seen.add(full)
        text = el.get_text(" ", strip=True) or el.get("value") or el.get("aria-label") or ""
        out.append({"href": full, "text": text})
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
