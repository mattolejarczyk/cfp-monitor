"""One rule for "can this market's research be used?", shared by the Saturday import and the recap.

WHY (2026-11-07, docs/design/inspection-2026-11-07.md defect 1). The research exit code was read two ways:
scripts/weekend_import.py accepted exit 1 since 2026-10-16 (one stub row must not hold back 94 good rows),
while scripts/weekend_recap.py still treated anything but exit 0 as FAILED. So the Friday 2026-11-06 recap said
FAILED for a run whose research was HEALTHY and whose load was DONE. The other way round, run_monthly.ps1
reports exit 0 even when both markets exited 1, so exit 0 proves nothing either. The exit code only tells
us about a HALT (3 out of quota, 4 search collapsed, 130 interrupted). Whether the OUTPUT is usable is what
the run itself recorded: the verdict in <Market>_audited.health.json (written by run_market_audit.py at the
end of every run, HEALTHY or DEGRADED today, FAILED reserved) and the row counts against the input list.

    from src.cfp_monitor.research_usable import check
    c = check("Cybersecurity", markets_dir, research_exit=1)
    c.usable        True / False
    c.why           the plain reason when not usable, "" when usable
    c.verdict       HEALTHY / DEGRADED / FAILED, or None when this run wrote no verdict
    c.notes         things a person should still hear when it IS usable (DEGRADED, no verdict file)

Quality by design: "could not look" is never reported as "nothing found". A missing verdict file is said,
a DEGRADED verdict is said, and a run that stopped short is not usable however healthy its calls were.
"""
from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

# Older than this and the output is not this weekend's research. Same value weekend_import carried.
MAX_OUTPUT_AGE_H = 30
# run_market_audit.py exit codes: 0 complete; 1 finished with stub rows or rows that did not land
# (routine, the row rule handles each one); 3 quota exhausted; 4 grounded search collapsed; 130 interrupted.
USABLE_EXITS = (None, 0, 1)
HALT_EXITS = "3 = out of quota, 4 = search collapsed, 130 = interrupted, 6 = HELD: the customer sheets or the customer context were not ready, so the research never started"


@dataclass
class ResearchCheck:
    market: str
    usable: bool
    why: str = ""
    verdict: str | None = None
    reasons: list[str] = field(default_factory=list)
    rows_due: int | None = None
    rows_out: int | None = None
    notes: list[str] = field(default_factory=list)

    def sentence(self) -> str:
        """One plain line for the recap."""
        v = self.verdict or "no health verdict written by this run"
        rows = (f"{self.rows_out} of {self.rows_due} due rows" if self.rows_due is not None and self.rows_out is not None
                else f"{self.rows_out} rows" if self.rows_out is not None else "no output")
        head = f"{self.market}: {'usable' if self.usable else 'NOT usable'} ({v}, {rows})"
        tail = [self.why] if self.why else []
        tail += [n for n in self.notes if not n.startswith("no health verdict")] if self.verdict else []
        return head + (" - " + "; ".join(tail) if tail else "")


def _read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def due_rows(input_csv: Path) -> int:
    """Input rows the run was meant to research. DUP_OF rows are skipped by the audit on purpose (one award
    listed twice); REFRESH_SKIP rows are the ones the refresh plan deliberately left (their last accepted
    version is carried over). Neither is "missing" when absent from the output."""
    return sum(1 for r in _read_rows(input_csv)
               if not (r.get("DUP_OF") or "").strip() and not (r.get("REFRESH_SKIP") or "").strip())


def read_health(markets_dir: Path, market: str, max_age_h: float = MAX_OUTPUT_AGE_H,
                now: float | None = None) -> tuple[str | None, list[str], str | None]:
    """(verdict, reasons, note). verdict is None, with the note saying why, when this run wrote none:
    the file is missing, older than this weekend's research, or unreadable."""
    hp = Path(markets_dir) / f"{market}_audited.health.json"
    if not hp.exists():
        return None, [], f"no health verdict ({hp.name} not written by this run)"
    age_h = ((now or time.time()) - hp.stat().st_mtime) / 3600
    if age_h > max_age_h:
        return None, [], f"no health verdict from this run ({hp.name} is {age_h:.0f}h old)"
    try:
        d = json.loads(hp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, [], f"no health verdict ({hp.name} unreadable: {type(e).__name__})"
    verdict = str(d.get("verdict") or "").strip().upper() or None
    reasons = [str(r) for r in (d.get("reasons") or [])]
    if verdict is None:
        return None, reasons, f"no health verdict ({hp.name} carries none)"
    return verdict, reasons, None


def check(market: str, markets_dir: Path, research_exit: int | None = None,
          max_age_h: float = MAX_OUTPUT_AGE_H, now: float | None = None) -> ResearchCheck:
    """THE rule. Read-only; never raises on a missing file (that is a finding, not a fault)."""
    markets_dir = Path(markets_dir)
    now = now or time.time()
    c = ResearchCheck(market=market, usable=False)
    if research_exit not in USABLE_EXITS:
        c.why = f"the research run exited {research_exit} ({HALT_EXITS})"
        return c
    out = markets_dir / f"{market}_audited.csv"
    if not out.exists():
        c.why = f"no research output at {out.name}"
        return c
    age_h = (now - out.stat().st_mtime) / 3600
    if age_h > max_age_h:
        c.why = f"{out.name} is {age_h:.0f}h old - this weekend's research did not write it"
        return c
    c.verdict, c.reasons, note = read_health(markets_dir, market, max_age_h, now)
    if note:
        c.notes.append(note)
    c.rows_out = len(_read_rows(out))
    inp = markets_dir / f"{market}_input.csv"
    if inp.exists():
        c.rows_due = due_rows(inp)
    if c.verdict == "FAILED":
        c.why = f"the research run's own verdict is FAILED" + (f" - {'; '.join(c.reasons)}" if c.reasons else "")
        return c
    if c.verdict == "DEGRADED":
        c.notes.append("RUN HEALTH DEGRADED" + (f" - {'; '.join(c.reasons)}" if c.reasons else "")
                       + " (loadable: the row rule judges each row; read the health file)")
    if c.rows_due is not None and c.rows_out < c.rows_due:
        c.why = f"{out.name} holds {c.rows_out} rows for {c.rows_due} input rows - the run stopped short"
        return c
    c.usable = True
    return c
