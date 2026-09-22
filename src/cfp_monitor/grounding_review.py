"""Turn the grounding trail's signals into decision-ready actions for the review step.

The trail (`<output>.grounding.jsonl`, written by run_market_audit.py) records a diagnostic
signal per row: `citation-host-not-in-sources` - the row searched, but the evidence URL it
wrote is on a host that never appeared among the hosts it searched, the usual signature of a
COMPOSED citation. That signal is deliberately NOT self-healed: rewriting a citation is exactly
what the acceptance gate protects against. So it belongs in a human's hands - but as a concise
"here is the issue, here is what to do", not a raw count.

This reads a run's trail and emits, per flagged row, one action line routed to the review step:
verify the cited page actually carries the claim, and if it does not, withdraw the citation
through the existing tools - never invent one. Advisory: it reports, it does not gate.
"""
import json
from pathlib import Path

# The cited page carries the claim? -> withdraw if not. Tools differ by row shape.
_VERIFY = {"Awards": "scripts/check_award_deadlines.py"}
_VERIFY_DEFAULT = "scripts/audit_evidence.py (or scripts/check_urls_against_site.py)"
_WITHDRAW = "scripts/mechanical_repairs.py"


def load_outcomes(jsonl_path):
    """The per-row outcome records from a .grounding.jsonl (research pass only)."""
    out = []
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("kind") == "outcome" and r.get("pass", "research") == "research":
            out.append(r)
    return out


def build_review(outcomes):
    """Split the outcomes into the two things a person can act on."""
    composed, no_search = [], []
    for o in outcomes:
        if o.get("searched") and not o.get("stub") and o.get("citation_host") \
                and o.get("citation_host_in_sources") is False:
            composed.append(o)
        elif not o.get("searched") or o.get("stub"):
            no_search.append(o)
    return {"composed": composed, "no_search": no_search}


def _verify_tool(opp_type):
    return _VERIFY.get(opp_type or "", _VERIFY_DEFAULT)


def render(review, name):
    composed, no_search = review["composed"], review["no_search"]
    lines = [f"GROUNDING REVIEW - {name}"]
    if not composed and not no_search:
        lines.append("  clean: every grounded row cited a host it searched, and no row stubbed.")
        return "\n".join(lines)
    lines.append(f"  {len(composed)} citation(s) to check, {len(no_search)} row(s) that ran no search.")
    lines.append("")

    if composed:
        lines.append("CITATION ON A HOST THAT WAS NOT SEARCHED  (usually a composed URL - check before it ships)")
        for o in composed:
            others = [h for h in o.get("source_hosts", []) if h != o["citation_host"]]
            shown = ", ".join(others[:4]) + (f", +{len(others) - 4} more" if len(others) > 4 else "")
            lines.append(f"- {o['row']}  [{o.get('opportunity_type') or '?'}]")
            lines.append(f"    cited {o['citation_host']}; searched {len(others)} other host(s)"
                         + (f": {shown}" if shown else ""))
            lines.append(f"    -> confirm the cited page states the claim ({_verify_tool(o.get('opportunity_type'))});")
            lines.append(f"       if it does not, withdraw the citation ({_WITHDRAW}) - never invent one.")
        lines.append("")

    if no_search:
        lines.append("NO SEARCH RAN  (shipped as honest stubs, not research)")
        for o in no_search:
            lines.append(f"- {o['row']}  [{o.get('opportunity_type') or '?'}]")
        lines.append("    -> re-run these rows with --redo-stubs once grounded search recovers.")

    return "\n".join(lines)


def review_file(jsonl_path):
    p = Path(jsonl_path)
    return render(build_review(load_outcomes(p)), p.name)
