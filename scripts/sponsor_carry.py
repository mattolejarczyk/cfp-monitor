"""Sponsorship carry-forward, option A ("never lose a known answer"). Pure function; no files, no network, no database.

    from scripts.sponsor_carry import carry_sponsorship
    rows, report = carry_sponsorship(rows, sources, prior_by_canon, lookup, to_canonical)

WHY (2026-10-02, docs/design/sponsorship-carry-forward.md, operator chose option A). Each Saturday's research asks again whether an
event requires paid sponsorship and what it costs. The FACT is stable (SPONSOR_REQUIRED changed on 1 of 76 events week over week)
but the wording and page churn weekly, and on 4 Cybersecurity events a cost we already knew came back BLANK. The row rule
(weekend_import.apply_row_rule) already keeps last week's approved version of a row that fails; this is the same idea one field
group down: do not let an Unknown or a blank replace an answer we already hold.

THE RULES (a row from this week's research, `sources[i] == "new"`, and a last-week approved row for the same canonical event)
  1. SAME EDITION ONLY. Both rows must state the same, non-blank EDITION. A new edition starts fresh: sponsorship terms change per year.
  2. Last week's answer must be RESOLVED: SPONSOR_REQUIRED is Yes or No. Unknown and blank are not an answer.
  3. This week's SPONSOR_REQUIRED is Unknown or blank  ->  carry last week's SPONSOR_REQUIRED, SPONSOR_URL, SPONSOR_COST and
     SPONSOR_QUOTE together, as one unit (gate R18b: a requirement carries its own evidence). Never carry the answer without its
     page.
  4. This week's SPONSOR_REQUIRED equals last week's  ->  fill only the cells that are BLANK this week (URL, COST, QUOTE) from last
     week. A non-blank cell this week is never touched (a fresh answer, however reworded, stands).
  5. This week's SPONSOR_REQUIRED DIFFERS from last week's (Yes vs No)  ->  nothing is carried and the change is REPORTED: it is a
     genuine change, or a genuine disagreement, for a person to look at.
  6. Every carry is reported (event, fields, why) so a carried value is never mistaken for fresh research.

It never changes any other column and never touches a row that is not this week's research. It does not stamp a date: the
`SOURCE_AS_OF` of the row stays this week's, so the report is the only record that a value was carried.
"""
from __future__ import annotations

SPONSOR_COLS = ("SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE")
RESOLVED = {"yes", "no"}


def _cell(row: dict, col: str) -> str:
    return (row.get(col) or "").strip()


def carry_sponsorship(rows: list[dict], sources: list[str], prior_by_canon: dict[str, dict], lookup: dict[str, str],
                      to_canonical) -> tuple[list[dict], dict]:
    """Returns (rows, report). `rows` is edited in place and returned; `report` lists every carry and every disagreement."""
    carried, disagreements, skipped_edition = [], [], 0
    for i, row in enumerate(rows):
        if sources[i] != "new":
            continue
        canon = to_canonical(row.get("EVENT_ID", ""), lookup)
        prior = prior_by_canon.get(canon)
        if prior is None or not all(c in row for c in SPONSOR_COLS):
            continue
        if not _cell(prior, "SPONSOR_REQUIRED").lower() in RESOLVED:
            continue                                                    # rule 2
        if not _cell(row, "EDITION") or _cell(row, "EDITION") != _cell(prior, "EDITION"):
            skipped_edition += 1                                        # rule 1
            continue
        new_req, old_req = _cell(row, "SPONSOR_REQUIRED").lower(), _cell(prior, "SPONSOR_REQUIRED").lower()
        name = row.get("CONFERENCE", "")
        if new_req in ("", "unknown"):                                  # rule 3: carry the unit
            fields = [c for c in SPONSOR_COLS if _cell(row, c) != _cell(prior, c)]
            for c in SPONSOR_COLS:
                row[c] = prior.get(c, "")
            if fields:
                carried.append({"conference": name, "canonical": canon, "fields": fields,
                                "why": "this week's answer was Unknown or blank; kept last week's resolved answer with its page"})
        elif new_req == old_req:                                        # rule 4: fill blanks only
            fields = [c for c in ("SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE") if not _cell(row, c) and _cell(prior, c)]
            for c in fields:
                row[c] = prior[c]
            if fields:
                carried.append({"conference": name, "canonical": canon, "fields": fields,
                                "why": "same answer as last week but these cells came back blank; filled from last week"})
        else:                                                           # rule 5: a real difference, reported
            disagreements.append({"conference": name, "canonical": canon, "last_week": old_req, "this_week": new_req})
    return rows, {"carried": carried, "disagreements": disagreements, "skipped_new_edition": skipped_edition}
