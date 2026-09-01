"""The documentation has a budget, and adding to it costs something.

WHY A TEST AND NOT A NOTE AT THE TOP OF THE FILE
Because a note at the top of the file is exactly the mechanism that has already failed. On
2026-09-01 three rules that were written down were broken anyway, on a day when four more
documents and two more judgement rules were added. The reflex under pressure is to write it
down; writing it down is what stopped working.

Growth here is not neutral. Every line lowers the odds that any GIVEN line is retrieved at the
moment it matters, and retrieval-at-the-moment is the whole failure mode. So the budget is
enforced, and a rule that becomes executable is expected to shrink to a pointer.

These caps are deliberately set AT today's size, not above it. There is no headroom to grow
into: the next addition has to displace something, which is the entire point.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JUDGEMENT = ROOT / "docs" / "operations" / "JUDGEMENT.md"
SKILL = ROOT / ".claude" / "skills" / "cfp-protocol" / "SKILL.md"

# Set at the exact size on 2026-09-01, with no headroom. The next addition has to displace
# something. Rule 17's conversion paid for today's two new rules; the growth beyond that is the
# cap explanation and the citation table - mechanism, not more examples, which is the only kind
# of growth this budget is meant to allow.
#
# THESE NUMBERS WERE WRONG ON THE FIRST ATTEMPT, at 321 and 190. They came from PowerShell's
# `Measure-Object -Line`, which counts a BLANK line as zero, so both files were a third longer
# than reported. The caps would have been set below the current size and failed immediately -
# which is how it was noticed. Measure with `len(text.splitlines())`; a counting tool that
# silently skips a category of input is the same shape as every other defect this file records.
MAX_RULES = 21
MAX_JUDGEMENT_LINES = 448
MAX_SKILL_LINES = 236


def _lines(p):
    return len(p.read_text(encoding="utf-8").splitlines())


def _flat(p):
    """Markdown wraps sentences across lines, so assert against normalised whitespace or the
    test fails on where a paragraph happens to break rather than on what it says."""
    return re.sub(r"\s+", " ", p.read_text(encoding="utf-8"))


def test_judgement_is_capped_at_21_rules():
    """A 22nd rule must displace one, or become a test. Both are better than a longer file."""
    n = len(re.findall(r"^## \d+\.", JUDGEMENT.read_text(encoding="utf-8"), re.M))
    assert n <= MAX_RULES, (
        f"JUDGEMENT.md has {n} rules, cap is {MAX_RULES}. Before adding one: can it be a test "
        f"instead, and which existing rule does it replace or merge into?")


def test_judgement_does_not_sprawl():
    n = _lines(JUDGEMENT)
    assert n <= MAX_JUDGEMENT_LINES, (
        f"JUDGEMENT.md is {n} lines, cap is {MAX_JUDGEMENT_LINES}. A rule that has become "
        f"executable should shrink to a pointer at its test - rule 17 is the worked example.")


def test_the_protocol_skill_does_not_sprawl():
    """This one is loaded at the start of every session, so its length is paid every time.
    Past a point, adding to it makes the rest of it less likely to be read."""
    n = _lines(SKILL)
    assert n <= MAX_SKILL_LINES, (
        f"cfp-protocol SKILL.md is {n} lines, cap is {MAX_SKILL_LINES}.")


def test_the_cap_is_stated_where_someone_adding_a_rule_will_see_it():
    """The test enforces it; the file has to explain it, or the failure is just an obstacle."""
    head = _flat(JUDGEMENT)[:2600]
    assert "capped at" in head
    assert "Can this be a test instead?" in head


def test_the_protocol_demands_a_citation_not_just_a_read():
    """Reading three documents at session start did not prevent three documented rules being
    broken four hours in. The gate is now: name the governing decision and where it is written,
    before writing the line."""
    s = _flat(SKILL)
    assert "Cite the decision BEFORE you write the line" in s
    assert "If you cannot cite it, you have not looked" in s
    # And the answers must be there, or the check is a chore rather than a lookup.
    for must in ("identity.to_canonical", "gviz", "customer_context.py", "contract 3"):
        assert must in s, f"the citation table must name {must}"


def test_rule_17_actually_shrank():
    """The claim in the header is that rule 17 was converted rather than merely annotated. If
    the paragraph creeps back, the cap is being satisfied on paper only."""
    txt = JUDGEMENT.read_text(encoding="utf-8")
    i = txt.index("## 17.")
    j = txt.index("## 18.", i)
    body = txt[i:j]
    assert len(body.splitlines()) <= 16, "rule 17 should be a short entry plus a pointer"
    assert "identity.py" in body and "test_identity_join.py" in body
