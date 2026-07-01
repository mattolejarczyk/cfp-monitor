"""Debuggable crawl decisions (feat 14).

A tiny append-only log of what the crawler found, prioritized, crawled, skipped —
and why. Attached to each ConferenceResult so a human (or a downstream agent) can
audit the run.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Tracer:
    events: list[dict] = field(default_factory=list)

    def log(self, action: str, url: str = "", reason: str = "", **extra) -> None:
        """Record one decision. `action` e.g. found | scored | crawled | skipped | extracted | error."""
        self.events.append(
            {"t": round(time.time(), 3), "action": action, "url": url, "reason": reason, **extra}
        )

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in self.events:
            out[e["action"]] = out.get(e["action"], 0) + 1
        return out

    def dump(self) -> list[dict]:
        return list(self.events)
