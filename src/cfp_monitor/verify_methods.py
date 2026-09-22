"""The one vocabulary for HOW a fact was verified - its provenance.

Every verification result and every stored confirmation names its METHOD from this registry, so
a fact can always be traced to how it was produced and how far to trust it. One definition,
imported everywhere (like the rules layer) - a method label that is not registered here is a
defect. Categorised on three axes so the data can be sliced any way: SOURCE (how the page was
obtained), MATCH (how the claim was confirmed), COST (what it spends).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Method:
    id: str
    label: str
    source: str        # derived | plain-http | real-browser | grounded-search | upstream
    match: str         # date-comparison | date-context-regex | llm-verbatim | none
    cost: str          # free | llm | grounded
    deterministic: bool
    note: str


_METHODS = [
    Method("deadline-passed", "Deadline already passed",
           source="derived", match="date-comparison", cost="free", deterministic=True,
           note="No page needed: the row's own deadline is in the past, so the call is CLOSED. "
                "not_found is expected and harmless here (a passed-deadline page comes down, v2.2) "
                "- there is nothing to confirm and no search is worth spending. The cheapest "
                "resolution, checked before any fetch."),
    Method("fetch-plain+regex", "Plain fetch + regex",
           source="plain-http", match="date-context-regex", cost="free", deterministic=True,
           note="Cheapest: a plain HTTP GET, deadline located by date-in-submission-context. A "
                "not_found row already failed this, so it re-confirms little - it is the floor."),
    Method("browser-ladder+regex", "Real-Chrome fetch + regex",
           source="real-browser", match="date-context-regex", cost="free", deterministic=True,
           note="Escalation for JS/403 pages a plain GET cannot read: the signed-in Chrome on "
                ":9222 (render_targets). No grounded quota; slower, seconds per page."),
    Method("llm-verbatim", "Model reads page, verbatim-checked",
           source="real-browser", match="llm-verbatim", cost="llm", deterministic=False,
           note="The model finds the sentence stating the known deadline; it must be a literal "
                "substring of the fetched page (locate_verbatim). For date forms the regex "
                "misses. Uses the OpenRouter model, not grounded quota."),
    Method("grounded-search+verify", "Grounded search, then verified",
           source="grounded-search", match="date-context-regex", cost="grounded", deterministic=False,
           note="The throttled exception: grounded Google search finds the CURRENT page when the "
                "cited one is stale; the answer is then fetched and the quote proven. Spends a "
                "grounded request - budgeted and human-paced."),
    Method("upstream-grounding", "Upstream grounded research",
           source="upstream", match="none", cost="grounded", deterministic=False,
           note="The original citation from upstream's grounded research (evidence.origin="
                "grounding). Recorded for provenance; not produced by self-heal."),
]

METHODS = {m.id: m for m in _METHODS}

# Convenience ids, so callers reference a constant, not a string literal.
DEADLINE_PASSED = "deadline-passed"
FETCH_PLAIN = "fetch-plain+regex"
BROWSER_LADDER = "browser-ladder+regex"
LLM_VERBATIM = "llm-verbatim"
GROUNDED = "grounded-search+verify"
UPSTREAM = "upstream-grounding"

FREE_METHODS = tuple(m.id for m in _METHODS if m.cost == "free")
GROUNDED_METHODS = tuple(m.id for m in _METHODS if m.cost == "grounded")


def is_method(mid: str) -> bool:
    return mid in METHODS


def describe(mid: str) -> Method | None:
    return METHODS.get(mid)
