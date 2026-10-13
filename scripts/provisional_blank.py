"""Which field of a held conference row failed its check, and so must be BLANKED when the row is shown as Provisional (ACT-70; QA-REGISTER A64). Read-only; changes nothing on disk.

    python scripts/provisional_blank.py --market Cybersecurity [--markets-dir <dir>] [--db <db>] [--on 2026-10-12]

WHY. Operator ruling 2026-10-13: the customer's sheets are the source of truth, so every conference they track is SHOWN, even when this week's research of it failed a check and is held out of
the approved file. A held row is shown Provisional (the same marker and sentence as an award) with the FAILING FIELD BLANKED, so we never show a detail we know is wrong: a venue typed into
CITY, a placeholder such as 'To Be Announced', unproven active-call prose on a projected row, a submit link that is a 404, a deadline whose quote is not on the page.

WHERE THE REASONS COME FROM (files only, no network, no model). For one market: every `weekend/<stamp>/weekend_import.log` and `<Market>_audited.candidate.gate.json` at or after the day the raw
research was written (the gate's own words: the `[FAIL] <check> <title>` blocks and the `- <name>: <detail>` lines under them), plus `market_sheets/held_rows.txt` (the row rule's reason per
permanent id, which can carry a gate failure as `[3] <name>: <detail>`) and the `NEW EVENT HELD (not loaded): <name> - <reason>` log lines. The mapping from check to field is
docs/operations/provisional_blank_rules.json. A row with a failure whose check has no mapping, and a row for which NO gate result was found, take the rule file's `default`.

MATCHING A FAILURE TO A ROW (the care weekend_import.rows_for_failure takes, plus the value the failure names). The gate cuts the name at 38 or 40 characters, so weekend_import.rows_for_failure
(prefix, greedy; narrowed by a date when the text names one) gives the first set; of that set the rows with the LONGEST name prefix are kept ('AppSec & DevSecOps (Corinium)' against '... Singapore');
then every value the failure names (a quoted string, a URL, CITY='x') must be found in a cell of the row, when that leaves at least one row. A row is never matched by an upstream id except through
the permanent id in held_rows.txt (which is already ours: identity.to_canonical)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

RULES_PATH = ROOT / "docs" / "operations" / "provisional_blank_rules.json"
NV = "Needs Verification"
LINK_FIELDS = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL", "CONFERENCE URL", "MAIN_INFO_URL", "VENUE_EVIDENCE_URL", "LIFECYCLE_EVIDENCE_URL", "SPONSOR_URL")
LINK_FALLBACK = ("SUBMISSION URL", "CFP_SUBMISSION_URL", "DEADLINE_EVIDENCE_URL")
STATUS_BLANKERS = ("SUBMISSION DEADLINE", "STATUS DETAILS")        # blanking either one means the status can no longer be stated: Needs Verification


def tidy(t) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


class Failure(dict):
    """{'check', 'title', 'text' ('<name>: <detail>' as the gate prints it), 'source', 'canon' (set when the reason is keyed by a permanent id)}"""

    def __init__(self, check: str, title: str, text: str, source: str, canon: str = ""):
        super().__init__(check=check, title=title, text=text, source=source, canon=canon)


def load_rules(path: Path = RULES_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ============================================================================ reading the reasons
def parse_log(text: str, market: str, source: str = "log") -> list[Failure]:
    """The `[FAIL]` blocks of every `ACCEPTANCE GATE - <market>_audited.candidate.csv` section of a weekend_import.log, as Failure items (NOTE blocks are advisory and hold nothing)."""
    out: list[Failure] = []
    in_market, check, title = False, "", ""
    for ln in text.splitlines():
        h = re.match(r"\s*ACCEPTANCE GATE - (\w+)_audited\.candidate\.csv", ln)
        if h:
            in_market, check, title = h.group(1) == market, "", ""
            continue
        if not in_market:
            continue
        m = re.match(r"\s*\[(PASS|FAIL|NOTE)\]\s+(\S+)\s+(.*?)\s*(?:\(\d+\))?\s*$", ln)
        if m:
            check, title = (m.group(2), m.group(3)) if m.group(1) == "FAIL" else ("", "")
            continue
        m = re.match(r"\s{6,}-\s+(.+?)\s*$", ln)
        if m and check:
            out.append(Failure(check, title, m.group(1), source))
        elif ln.strip().startswith("RESULT:"):
            in_market, check = False, ""
    return out


def parse_gate_json(data: dict, market: str, source: str = "gate.json") -> list[Failure]:
    out: list[Failure] = []
    for _fname, checks in (data or {}).items():
        if not str(_fname).startswith(f"{market}_audited"):
            continue
        for c in checks or []:
            if c.get("passed"):
                continue
            for f in c.get("failures") or []:
                if isinstance(f, str) and not f.startswith("SKIPPED"):
                    out.append(Failure(str(c.get("check")), str(c.get("name") or ""), f, source))
    return out


def parse_held_rows(text: str, market_scope: set[str] | None = None) -> list[Failure]:
    """market_sheets/held_rows.txt: `<permanent id>  # AUTO <date> weekend_import - held back from this week's file by the row rule: <reason>`. A reason that begins `[3] name: detail` is a gate
    failure (check 3) keyed by the permanent id; anything else is a row-rule reason (check 'row-rule')."""
    out: list[Failure] = []
    for ln in text.splitlines():
        if "#" not in ln or ln.lstrip().startswith("#"):
            continue
        k, why = ln.split("#", 1)
        k = k.strip()
        if not k:
            continue
        m = re.search(r"held back from this week's file by the row rule: (.+)$", why)
        if not m:
            continue
        reason = m.group(1).strip()
        g = re.match(r"\[(\S+)\]\s+(.+)$", reason)
        if g:
            out.append(Failure(g.group(1), "", g.group(2), "held_rows.txt", canon=k))
        else:
            out.append(Failure("row-rule", "", reason, "held_rows.txt", canon=k))
    return out


def parse_new_event_held(text: str, market: str) -> list[Failure]:
    out = []
    for m in re.finditer(r"\[" + re.escape(market) + r"\] NEW EVENT HELD \(not loaded\): (.{3,70}?) - (.+)", text):
        out.append(Failure("row-rule", "", f"NEW EVENT HELD: {m.group(1).strip()}: {m.group(2).strip()}", "log"))
    return out


def stamp_of(folder: Path) -> datetime | None:
    try:
        return datetime.strptime(folder.name, "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def collect_failures(markets_dir: Path, market: str, raw_path: Path | None, data_root: Path | None = None) -> tuple[list[Failure], list[str]]:
    """-> (failures, notes). Folders `weekend/<stamp>` from the day the raw research was written onward (union: a failure from any of them counts; blanking more is the safe error)."""
    notes: list[str] = []
    failures: list[Failure] = []
    since = datetime.fromtimestamp(Path(raw_path).stat().st_mtime).date() if raw_path and Path(raw_path).exists() else None
    wk = Path(markets_dir) / "weekend"
    folders = sorted(p for p in wk.glob("*") if p.is_dir()) if wk.is_dir() else []
    used = 0
    for f in folders:
        st = stamp_of(f)
        if since and st and st.date() < since:
            continue
        got = False
        lp = f / "weekend_import.log"
        if lp.exists():
            txt = lp.read_text(encoding="utf-8", errors="replace")
            failures += parse_log(txt, market, f"{f.name}/weekend_import.log")
            failures += parse_new_event_held(txt, market)
            got = True
        gp = f / f"{market}_audited.candidate.gate.json"
        if gp.exists():
            try:
                failures += parse_gate_json(json.loads(gp.read_text(encoding="utf-8")), market, f"{f.name}/{gp.name}")
                got = True
            except (OSError, ValueError):
                notes.append(f"{gp} could not be read")
        used += int(got)
    if not used:
        notes.append(f"no weekend_import.log or gate file found under {wk} since the raw research was written: every row takes the default blanking")
    hp = Path(data_root) / "market_sheets" / "held_rows.txt" if data_root else None       # the folder the database sits in (callers pass db.parent)
    if hp is not None and hp.exists():
        failures += parse_held_rows(hp.read_text(encoding="utf-8", errors="replace"))
    return failures, notes


# ============================================================================ matching a failure to a row
NAME_PREFIX = 38


def _named_values(text: str) -> list[str]:
    """The values a failure names: quoted strings, FIELD='x' values and URLs (a quote the gate cut is still a prefix of the cell, which `in` finds)."""
    vals = re.findall(r"=\s*'([^']{3,})'", text) + re.findall(r'"([^"]{4,})"', text) + re.findall(r"https?://[^\s'\")]+", text)
    return [v.strip().rstrip("/") for v in vals if v.strip()]


def match_rows(failure: Failure, rows: list[dict], canon_of=None) -> list[int]:
    """Indexes of `rows` this failure names. A permanent-id keyed reason matches by `canon_of(row)`; a gate failure by name prefix (weekend_import.rows_for_failure), the longest prefix first,
    then by the values it names."""
    if failure["canon"]:
        return [i for i, r in enumerate(rows) if canon_of and canon_of(r) == failure["canon"]]
    try:
        from scripts.weekend_import import rows_for_failure
    except Exception:                                                       # noqa: BLE001
        def rows_for_failure(text, rs):                                     # same rule, kept in step with weekend_import
            return [i for i, r in enumerate(rs) if tidy(r.get("CONFERENCE")) and text.startswith(tidy(r.get("CONFERENCE"))[:NAME_PREFIX])]
    text = failure["text"]
    hits = rows_for_failure(text, [{**r, "CONFERENCE": tidy(r.get("CONFERENCE"))} for r in rows])
    if len(hits) > 1:
        longest = max(len(tidy(rows[i].get("CONFERENCE"))[:NAME_PREFIX]) for i in hits)
        hits = [i for i in hits if len(tidy(rows[i].get("CONFERENCE"))[:NAME_PREFIX]) == longest]
    if len(hits) > 1:
        vals = _named_values(text)
        if vals:
            narrowed = [i for i in hits if all(any(v.lower() in (c or "").lower() for c in rows[i].values()) for v in vals)]
            if narrowed:
                hits = narrowed
    return hits


# ============================================================================ the blanking
def _rule_for(f: Failure, rules: dict) -> dict:
    if f["check"] == "row-rule":
        low = f["text"].lower()
        for rr in rules.get("row_rule_reasons", []):
            if rr["match"].lower() in low:
                return rr
        return {**rules["default"], "why": "a reason with no mapping: " + f["text"][:80]}
    r = (rules.get("gate_checks") or {}).get(f["check"])
    if r is None or r.get("use_default"):
        return {**rules["default"], "why": f"check {f['check']} has no field mapping"}
    return r


def _expand(tokens: list[str], f: Failure, row: dict) -> list[str]:
    out: list[str] = []
    for t in tokens:
        if t == "@named":
            m = re.search(r"\b([A-Z][A-Z0-9_ ]*[A-Z0-9])\s*=\s*'", f["text"])
            if m and m.group(1) in row:
                out.append(m.group(1))
            else:
                out += [x for x in ("CITY", "LOCATION") if re.search(r"\b" + x + r"\b", f["text"])]
        elif t == "@url":
            urls = [u.lower().rstrip("/") for u in re.findall(r"https?://[^\s'\")]+", f["text"])]
            hit = [c for c in LINK_FIELDS if urls and tidy(row.get(c)).lower().rstrip("/") in urls]
            out += hit or [c for c in LINK_FALLBACK]
        else:
            out.append(t)
    return out


def apply_blanks(row: dict, failures: list[Failure], rules: dict, checked: bool = True) -> tuple[dict, list[str], list[str]]:
    """-> (a copy of the row with the failing fields blanked, [fields actually blanked], [plain reasons]). `checked` False = no gate result found for the row (the default blanking applies)."""
    r = dict(row)
    fields: list[str] = []
    why: list[str] = []
    status = None
    if not failures:
        rules_used = [({**rules["default"]}, None)]
        why.append("no gate result was found for this row, so the default fields are blanked" if not checked else rules["default"]["why"])
    else:
        rules_used = [(_rule_for(f, rules), f) for f in failures]
    for rule, f in rules_used:
        toks = rule.get("blank", [])
        fields += _expand(toks, f, r) if f else [t for t in toks]
        if f:
            detail = f["text"].split(":", 1)[1].strip()[:80] if ":" in f["text"] else ""
            why.append(f"check {f['check']} {rule.get('why') or rule.get('title') or ''}".strip() + (f" ({detail})" if detail else ""))
        st = rule.get("status")
        if st:
            status = st if status in (None, "@derive") else status
    done = []
    for fld in dict.fromkeys(fields):
        if fld in r and tidy(r.get(fld)):
            done.append(fld)
        if fld in r:
            r[fld] = ""
    if any(fld in done for fld in STATUS_BLANKERS):
        status = NV
    if status == NV:
        r["STATUS"] = NV
    return r, done, why
