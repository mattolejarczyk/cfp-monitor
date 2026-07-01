"""CFP / speaking-opportunity vocabulary used for scoring and classification.

Central so URL discovery, link/button scoring, and crawl prioritization all agree
on what "relevant" means (feat 3, 4).
"""

# Phrases that signal a speaking/submission opportunity. Used by the crawl4ai
# KeywordRelevanceScorer and by our own link/button classifier.
CFP_KEYWORDS: list[str] = [
    "call for papers",
    "call for speakers",
    "call for proposals",
    "call for presentations",
    "speaker application",
    "propose a talk",
    "submit a talk",
    "submit a proposal",
    "submit a session",
    "submit an abstract",
    "abstract submission",
    "proposal submission",
    "paper submission",
    "become a speaker",
    "speak at",
    "cfp",
    "submit",
    "submission",
    "speakers",
    "call for",
    # PR / awards / industry-event flavor (call for ENTRIES / NOMINATIONS):
    "call for entries",
    "call for nominations",
    "call for entry",
    "submit an entry",
    "submit a nomination",
    "enter now",
    "enter the awards",
    "nominate",
    "nominations",
    "nomination",
    "awards",
    "how to enter",
    "entry deadline",
    "entry kit",
]

# Secondary context pages worth crawling (dates/status/where-to-submit live here).
CONTEXT_KEYWORDS: list[str] = [
    "important dates",
    "key dates",
    "deadlines",
    "program",
    "agenda",
    "schedule",
    "tracks",
    "workshops",
    "speakers",
    "sessions",
    "faq",
    "about",
]

# URL-path fragments that usually indicate a relevant page (wildcards for
# crawl4ai's URLPatternFilter are added in scoring.py).
CFP_URL_HINTS: list[str] = [
    "cfp",
    "call-for",
    "callforpapers",
    "call-for-papers",
    "call-for-speakers",
    "speak",
    "speaker",
    "submit",
    "submission",
    "proposal",
    "propose",
    "abstract",
    "presentations",
    "important-dates",
    "dates",
    "program",
    "agenda",
    "schedule",
    "tracks",
    "sessions",
    # PR / awards flavor
    "entries",
    "entry",
    "enter",
    "nominate",
    "nominations",
    "nomination",
    "awards",
    "categories",
]

# Known third-party submission platforms — a link to one of these is a strong
# "here is where you submit" signal even though it's off the conference domain.
SUBMISSION_PLATFORMS: dict[str, str] = {
    "sessionize.com": "Sessionize",
    "papercall.io": "PaperCall",
    "easychair.org": "EasyChair",
    "cmt3.research.microsoft.com": "Microsoft CMT",
    "openreview.net": "OpenReview",
    "pretalx.com": "pretalx",
    "hotcrp.com": "HotCRP",
    "linklings.net": "Linklings",
    "oxfordabstracts.com": "Oxford Abstracts",
    "conftool.net": "ConfTool",
    "google.com/forms": "Google Forms",
    "docs.google.com/forms": "Google Forms",
    "airtable.com": "Airtable",
    "typeform.com": "Typeform",
}
