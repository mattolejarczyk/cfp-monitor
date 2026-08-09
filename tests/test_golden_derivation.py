"""Golden master over every derivation the pipeline applies to a delivery.

WHY THIS EXISTS
On 2026-08-08 `clean_city` was found to be corrupting 23 of the 26 rows it claimed to
repair - Seattle became Washington, Tokyo became Tokyo Big Sight - and because the canonical
key derives from the city, 24 EVENT_IDs were wrong too. The whole suite passed throughout.
It passed because every existing test asserted that the function FIXES broken input; none
asserted that it LEAVES GOOD INPUT ALONE.

That is the general shape of the risk here. These rules were all correct once. `clean_city`
was right in July, when grounding really did put venues in CITY; upstream fixed their side
and ours silently turned from a repair into a corruption. A golden master catches exactly
that: it does not care whether the output is RIGHT, only whether it CHANGED. Any edit to
derivation logic produces an explicit diff that a human approves or rejects.

WHAT IS COVERED
Everything `normalize_rows` derives: the canonical EVENT_ID, the repaired CITY, the
normalized CFP model, placeholder scrubbing, dedupe behaviour, and the report counters.

WHY THE FIXTURE IS SYNTHETIC
`cfp-monitor` is a PUBLIC repository and the real delivery is the customer's asset, so it is
not committed here. Each fixture row instead reproduces one documented ruling or one real
defect, named so a failure says what broke. For a golden master over the real 406 rows, see
`scripts/snapshot_delivery.py`, which writes into the private upstream repo.

RE-BLESSING
If a diff is intended, review every line of it, then:

    python tests/test_golden_derivation.py --bless

Never bless without reading the diff. Blessing a corruption is how it becomes permanent.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.grounding import load_master_csv          # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "derivation_cases.csv"
GOLDEN = Path(__file__).parent / "fixtures" / "derivation_golden.json"

# Pinned so the snapshot never depends on the day it runs. Any derivation that varies with
# the date belongs at DISPLAY time (contract 2.2), not in stored output - if pinning this
# ever stops making a test deterministic, that itself is the finding.
TODAY = date(2026, 8, 8)


def derive() -> dict:
    rows, report = load_master_csv(str(FIXTURE), TODAY)
    return {
        "rows": [
            {
                "name": r.name,
                "market": r.market,
                "event_id": r.event_id,
                "city": r.city,
                "cfp_model": r.cfp_model,
                "deadline": r.deadline,
                "deadline_quote": r.deadline_quote,
                "is_projected": r.is_projected,
                "source_as_of": r.source_as_of,
                "issues": sorted(r.issues),
            }
            for r in rows
        ],
        "report": {
            "input": report["input"],
            "kept": report["kept"],
            "duplicates": report["duplicates"],
            "city_repaired": report["city_repaired"],
            "model_normalized": report["model_normalized"],
            "issue_counts": dict(sorted(report["issue_counts"].items())),
        },
    }


def _diff(expected: dict, actual: dict) -> list[str]:
    """A readable, line-oriented diff. A golden master nobody can read gets blessed blindly."""
    out: list[str] = []
    exp_rows = {(r["name"], r["market"]): r for r in expected["rows"]}
    act_rows = {(r["name"], r["market"]): r for r in actual["rows"]}

    for key in sorted(set(exp_rows) - set(act_rows)):
        out.append(f"ROW DISAPPEARED: {key[0]} [{key[1]}]")
    for key in sorted(set(act_rows) - set(exp_rows)):
        out.append(f"ROW APPEARED:    {key[0]} [{key[1]}]")
    for key in sorted(set(exp_rows) & set(act_rows)):
        e, a = exp_rows[key], act_rows[key]
        for field in e:
            if e[field] != a.get(field):
                out.append(f"{key[0]} [{key[1]}] . {field}\n"
                           f"    was: {e[field]!r}\n"
                           f"    now: {a.get(field)!r}")
    for field, was in expected["report"].items():
        now = actual["report"].get(field)
        if was != now:
            out.append(f"report.{field}\n    was: {was!r}\n    now: {now!r}")
    return out


def test_derivation_matches_golden():
    assert GOLDEN.exists(), (
        f"No golden snapshot at {GOLDEN}. Create it with:\n"
        f"    python tests/test_golden_derivation.py --bless")
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = derive()
    diff = _diff(expected, actual)
    assert not diff, (
        "Derivation output changed against the golden master.\n\n"
        + "\n".join(diff)
        + "\n\nIf every line above is an intended improvement, re-bless with:\n"
          "    python tests/test_golden_derivation.py --bless\n"
          "If any line is a surprise, it is a regression - 24 canonical keys were silently\n"
          "corrupted on 2026-08-08 by a change that looked like a tidy-up.")


# ---- the named cases, asserted directly ------------------------------------
# The golden master catches CHANGE; these say what CORRECT is, so a blessed-in corruption
# still fails. Both layers are needed: the snapshot alone would happily enshrine a bug.

def _by(name: str) -> dict:
    return next(r for r in derive()["rows"] if r["name"].startswith(name))


def test_a_venue_in_city_is_still_repaired():
    """The reason clean_city exists. Must keep working."""
    assert _by("Venue Still In City")["city"] == "Berlin"


def test_a_good_city_survives_blank_state_and_country():
    """Regression 2026-08-08: became 'Washington'."""
    assert _by("Good City Blank State")["city"] == "Seattle"


def test_a_good_city_survives_city_equals_state():
    """Regression 2026-08-08: became 'Tokyo Big Sight', and the key with it."""
    row = _by("City Equals State")
    assert row["city"] == "Tokyo"
    assert "big-sight" not in row["event_id"]


def test_city_state_is_preserved():
    assert _by("True City State")["city"] == "Hong Kong"


def test_postcode_never_enters_the_city():
    row = _by("Postcode In Location")
    assert row["city"] == "Heidelberg"
    assert "69115" not in row["event_id"]


def test_blank_city_is_parsed_from_location():
    assert _by("Blank City Parse Location")["city"] == "Las Vegas"


def test_tbd_yields_a_blank_city_never_an_invention():
    assert _by("Location Is TBD")["city"] == ""


def test_speaking_is_unsuffixed_and_other_types_are_not():
    assert not _by("Regional Sibling Europe")["event_id"].endswith("-speaking")
    assert _by("Suffixed Opportunity")["event_id"].endswith("-exhibiting")


def test_regional_siblings_get_distinct_keys():
    """Contract section 10: Europe and USA are distinct events sharing most of their words."""
    assert _by("Regional Sibling Europe")["event_id"] != _by("Regional Sibling USA")["event_id"]


def test_one_event_in_two_markets_keeps_one_key_and_both_rows():
    """Market is excluded from the key so one event is one record, but both memberships
    survive - dedupe is on (event_id, market)."""
    rows = [r for r in derive()["rows"] if r["name"].startswith("Multi Market Event")]
    assert len(rows) == 2
    assert rows[0]["event_id"] == rows[1]["event_id"]


def test_an_exact_repeat_is_deduped():
    rows = [r for r in derive()["rows"] if r["name"].startswith("Exact Duplicate Row")]
    assert len(rows) == 1
    assert derive()["report"]["duplicates"] == 1


def test_placeholders_are_scrubbed_not_carried():
    row = _by("Placeholder In Quote")
    assert row["deadline_quote"] == ""
    assert row["source_as_of"] == ""


def _bless() -> int:
    actual = derive()
    if GOLDEN.exists():
        diff = _diff(json.loads(GOLDEN.read_text(encoding="utf-8")), actual)
        if not diff:
            print("No change - golden master already matches.")
            return 0
        print("About to bless the following changes:\n")
        print("\n".join(diff))
        print()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(actual, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"Blessed -> {GOLDEN}  ({len(actual['rows'])} rows)")
    return 0


if __name__ == "__main__":
    if "--bless" in sys.argv:
        raise SystemExit(_bless())
    print(json.dumps(derive(), indent=2, ensure_ascii=False))
