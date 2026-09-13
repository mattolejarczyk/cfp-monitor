"""Run health: every run counts its own failures and says so, instead of being audited afterwards.

QUALITY BY DESIGN. On 2026-09-13 a crawl run reported "nothing found" for eleven sites. The
truth, found only by reading 112 suppressed error banners by hand, was that the page-reading LLM
had been rate-limited on nearly every page: the run had not looked, not failed to find. The same
day produced a Gemini call hung for 77 minutes, 504s and empty replies on most pilot calls, and
answers built from searches that were never checked for having run. Each was discovered in
retrospect. A run that cannot tell "nothing there" from "could not look" is not a result.

So a step records what it attempted and how each attempt ended, and the run ends with a verdict:

    HEALTHY    every check's failure rate is within its threshold
    DEGRADED   at least one check failed more than it may - its outcomes are not trustworthy

The verdict is printed and written into the run's summary, and callers can exit non-zero on it,
so a degraded run cannot be mistaken for a clean one.

    from src.cfp_monitor.run_health import HEALTH
    HEALTH.ok("page_read")
    HEALTH.fail("page_read", "rate_limited", url)
    HEALTH.note("page_read", "retried")          # informational, never a failure
    status, reasons = HEALTH.verdict()
"""
from __future__ import annotations

from collections import Counter, defaultdict

# A check with fewer attempts than this is judged only on hard failures, not on its rate:
# one failed read out of two is noise, not a finding.
MIN_ATTEMPTS = 5
# Default share of attempts that may fail before the check is DEGRADED. Chosen so today's crawl
# (most reads failing) trips it and an ordinary run with a stray timeout does not.
MAX_FAIL_RATE = 0.20
# Reasons that make a run DEGRADED on their own, whatever the rate: the run did something that
# must never pass silently.
HARD_FAILURES = {"quota_exhausted", "hung", "gate_crashed"}


class RunHealth:
    def __init__(self, name: str = "run"):
        self.name = name
        self.counts: dict[str, Counter] = defaultdict(Counter)
        self.notes: dict[str, Counter] = defaultdict(Counter)
        self.examples: dict[tuple[str, str], list[str]] = defaultdict(list)
        self.thresholds: dict[str, float] = {}

    # ---- recording ------------------------------------------------------------------------
    def ok(self, check: str, n: int = 1) -> None:
        self.counts[check]["ok"] += n

    def fail(self, check: str, reason: str, detail: str = "") -> None:
        self.counts[check][reason] += 1
        ex = self.examples[(check, reason)]
        if detail and len(ex) < 3:
            ex.append(str(detail)[:160])

    def note(self, check: str, what: str, n: int = 1) -> None:
        self.notes[check][what] += n

    def threshold(self, check: str, max_fail_rate: float) -> None:
        self.thresholds[check] = max_fail_rate

    def merge(self, other: dict) -> None:
        """Fold in a health block produced by another process (to_dict())."""
        for check, c in other.get("counts", {}).items():
            self.counts[check].update(c)
        for check, c in other.get("notes", {}).items():
            self.notes[check].update(c)
        for key, ex in other.get("examples", {}).items():
            check, _, reason = key.partition("|")
            self.examples[(check, reason)].extend(ex[: 3 - len(self.examples[(check, reason)])])

    # ---- reading --------------------------------------------------------------------------
    def attempts(self, check: str) -> int:
        return sum(self.counts[check].values())

    def failures(self, check: str) -> int:
        return self.attempts(check) - self.counts[check]["ok"]

    def snapshot(self, check: str) -> Counter:
        return Counter(self.counts[check])

    def verdict(self) -> tuple[str, list[str]]:
        reasons = []
        for check in sorted(self.counts):
            c, n, bad = self.counts[check], self.attempts(check), self.failures(check)
            hard = [r for r in c if r in HARD_FAILURES and c[r]]
            if hard:
                reasons.append(f"{check}: {', '.join(f'{c[r]} {r}' for r in hard)}")
                continue
            limit = self.thresholds.get(check, MAX_FAIL_RATE)
            if n >= MIN_ATTEMPTS and bad / n > limit:
                top = ", ".join(f"{v} {k}" for k, v in c.most_common() if k != "ok")
                reasons.append(f"{check}: {bad} of {n} failed ({bad / n:.0%}, limit "
                               f"{limit:.0%}) - {top}")
        return ("DEGRADED" if reasons else "HEALTHY"), reasons

    def to_dict(self) -> dict:
        return {"counts": {k: dict(v) for k, v in self.counts.items()},
                "notes": {k: dict(v) for k, v in self.notes.items()},
                "examples": {f"{c}|{r}": v for (c, r), v in self.examples.items()}}

    def report_lines(self) -> list[str]:
        status, reasons = self.verdict()
        lines = [f"## Run health: {status}", ""]
        lines += [f"- **{r}**" for r in reasons]
        if reasons:
            lines.append("")
        if not self.counts:
            return lines + ["(nothing was recorded)"]
        lines += ["| Check | Attempts | OK | Failed | By reason | Notes |", "|---|---|---|---|---|---|"]
        for check in sorted(self.counts):
            c = self.counts[check]
            by = ", ".join(f"{k} {v}" for k, v in c.most_common() if k != "ok") or "-"
            notes = ", ".join(f"{k} {v}" for k, v in self.notes[check].most_common()) or "-"
            lines.append(f"| {check} | {self.attempts(check)} | {c['ok']} | "
                         f"{self.failures(check)} | {by} | {notes} |")
        ex = [(k, v) for k, v in self.examples.items() if v]
        if ex:
            lines += ["", "Examples:"]
            for (check, reason), items in ex:
                lines += [f"- {check} / {reason}: {i}" for i in items]
        return lines

    def banner(self) -> str:
        status, reasons = self.verdict()
        return f"RUN HEALTH: {status}" + (f" - {'; '.join(reasons)}" if reasons else "")


HEALTH = RunHealth("process")
