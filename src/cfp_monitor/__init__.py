"""cfp_monitor — agentic Call-for-Papers detector built on crawl4ai."""
from .config import Settings, DEFAULT
from .models import ConferenceResult, PageExtraction, CFPStatus, Confidence, Fact, Evidence
from .pipeline import run_urls, analyze_conference

__all__ = [
    "Settings",
    "DEFAULT",
    "ConferenceResult",
    "PageExtraction",
    "CFPStatus",
    "Confidence",
    "Fact",
    "Evidence",
    "run_urls",
    "analyze_conference",
]

__version__ = "0.1.0"
