"""Guards for the mistakes that documentation did not stop.

Every rule here was written down somewhere before it was broken, and being written down did not
help. `docs/operations/customer-sheet-matching.md` has said since 2026-08-13 not to copy the
delivery's EVENT_ID across and not to use the gviz export endpoint. Both were done on
2026-09-01 by someone who had read the file that day.

So these are tests. A test fires at the moment of the mistake; a document fires only if someone
happens to re-read the right paragraph at the right minute, four hours into a session.

The pattern is copied from `test_no_reimplemented_crawling.py`, which works: it stopped a
duplicated site-walker the same day it would have shipped.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _py(*dirs):
    for d in dirs:
        for p in sorted((ROOT / d).glob("*.py")):
            yield p, p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- the id boundary --
def test_the_translation_lives_in_the_rules_layer():
    """One function, one name, in src - not a private helper inside a script that five other
    scripts reach into through a sys.path hack."""
    from src.cfp_monitor import identity
    assert hasattr(identity, "seed_map")
    assert hasattr(identity, "to_canonical")
    assert hasattr(identity, "assert_mapped")


# Scripts that parse the seed files themselves. Six, found by this test on its first run -
# the duplication was wider than anyone knew, which is the argument for the test rather than
# against it. Migrate to identity.seed_map and delete from this list.
#
# THE LIST MAY SHRINK. IT MUST NEVER GROW. Same contract as PENDING_MIGRATION in
# test_no_reimplemented_crawling.py: refactoring six scripts on the day the duplication is
# found is the large uninstrumented change this project keeps getting hurt by, so the debt is
# recorded by name and anything NEW fails.
OWN_SEED_PARSER = {
    "check_invariants.py":       "reconciles the database against a delivery",
    "import_grounding.py":       "writes the seed map as a side effect of importing",
    "make_handback.py":          "builds the upstream hand-back",
    "unconfirmed_citations.py":  "groups citations for upstream",
    "verify_grounding.py":       "layers 0/1/2 verification",
    "verify_report.py":          "renders the verification report",
}


def test_no_NEW_script_reimplements_the_seed_map():
    """The map is read from *_seed.csv and keyed EVENT_ID -> EVENT_ID_CANON. A second copy of
    that loop is how two implementations drift and one silently returns nothing - which reads
    as an empty result rather than a broken join."""
    offenders = []
    for p, src in _py("scripts", "src/cfp_monitor"):
        if p.name in ("identity.py", "apply_resolutions.py") or p.name in OWN_SEED_PARSER:
            continue
        if "EVENT_ID_CANON" in src and "_seed.csv" in src:
            offenders.append(p.name)
    assert not offenders, (
        f"these read the seed files directly instead of calling identity.seed_map: {offenders}. "
        f"If duplication is genuinely necessary, add the file to OWN_SEED_PARSER with a reason.")


def test_the_debt_list_does_not_grow_silently():
    """Six is the number on 2026-09-01. Recording it means a seventh needs a decision, not a
    shrug - and that every entry removed is visible progress."""
    assert len(OWN_SEED_PARSER) <= 6, (
        "OWN_SEED_PARSER grew. It may shrink; it must never grow.")
    for name in OWN_SEED_PARSER:
        assert (ROOT / "scripts" / name).is_file(), (
            f"{name} no longer exists - remove it from OWN_SEED_PARSER")


def test_the_old_private_name_still_works_but_only_delegates():
    """Five scripts import scripts.apply_resolutions._seed_map. It must keep working, and it
    must not keep a second copy of the logic."""
    src = (ROOT / "scripts" / "apply_resolutions.py").read_text(encoding="utf-8")
    i = src.index("def _seed_map(")
    body = src[i:i + 1400]
    assert "identity.seed_map" in body, "must delegate"
    assert "EVENT_ID_CANON" not in body, "must not still parse the seeds itself"


# ---------------------------------------------------------------- the export endpoint --
def test_nothing_uses_the_gviz_export():
    """`customer-sheet-matching.md` line 41: "Do not use /gviz/tq?tqx=out:csv".

    Used anyway on 2026-09-01. It types each column and silently drops non-conforming text -
    eight "Sponsorship Required - $12,500" deadlines and five free-text notification dates
    became blanks, and the diff reported them as thirteen customer edits. Had that shipped it
    would have told the customer they had deleted the very $12,500 figure we had just flagged
    to them as urgent.

    The working endpoint is /export?format=csv."""
    offenders = []
    for p, src in _py("scripts", "src/cfp_monitor"):
        if p.name == "test_identity_join.py":
            continue
        for m in re.finditer(r"gviz/tq", src):
            line = src[:m.start()].count("\n") + 1
            ctx = src[max(0, m.start() - 200):m.start()]
            if "Do not use" in ctx or "LOSSY" in ctx or "never" in ctx.lower():
                continue          # a warning ABOUT it is fine
            offenders.append(f"{p.name}:{line}")
    assert not offenders, f"gviz export is lossy and forbidden: {offenders}"


# ---------------------------------------------------------------- the customer's fields --
def test_nothing_writes_a_customer_owned_field():
    """`status`, `status_details`, `priority` and `NOTES` are the customer's under contract
    section 3. We read them to choose our work and to catch contradictions. Writing one - or
    "correcting" a row they marked Declined - is not ours to do."""
    owned = ("status", "status_details", "priority")
    offenders = []
    for p, src in _py("scripts", "src/cfp_monitor"):
        for col in owned:
            # An UPDATE naming the column, or an assignment into a client row.
            if re.search(rf"UPDATE\s+client_conferences[^;]*\bSET\b[^;]*\b{col}\b", src, re.I):
                offenders.append(f"{p.name}: writes client_conferences.{col}")
    assert not offenders, offenders


def test_the_client_layer_is_read_before_a_row_is_remediated():
    """The habit that cost a day on 2026-09-01: 22 rows repaired that the customer had already
    verified or acted on, two of them contradictions we were about to ship. The tool exists and
    the protocol requires it - this asserts both still do."""
    assert (ROOT / "scripts" / "customer_context.py").is_file()
    skill = (ROOT / ".claude" / "skills" / "cfp-protocol" / "SKILL.md").read_text(
        encoding="utf-8")
    assert "customer_context.py" in skill
    assert "before remediating" in skill.lower()
