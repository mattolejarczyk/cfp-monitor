"""Run the customer conference lists and write a clean coverage report (M5 presentation).

Usage:
  python scripts/coverage_run.py            # both customer xlsx lists
  python scripts/coverage_run.py <file.xlsx|urls.txt> ...   # explicit inputs

Writes, per input, into runs_out/coverage/:
  <stem>.md   - counts (worked/failed) + failed links with reasons + PARTIAL list
  <stem>.csv  - full per-URL detail (url, verdict, reason, name, canonical)
Plus a combined ROLLUP.md across all inputs. Uses row context from .xlsx so aggregator
navigation is exercised.
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cfp_monitor import run_urls, Settings
from src.cfp_monitor.goldset import load_inputs
from src.cfp_monitor.coverage import summarize, coverage_markdown, coverage_csv_rows

DESKTOP = "C:/Users/matts/Desktop/Nicolia-PR-Prime"
DEFAULT_LISTS = [
    ("Utility Global Conference List", f"{DESKTOP}/Utility Global Conference List 2026.xlsx"),
    ("Arnica Conferences (cyber)", f"{DESKTOP}/Arnica Conferences 2026.xlsx"),
]

OUT = "runs_out/coverage"


async def main() -> int:
    args = sys.argv[1:]
    lists = [(os.path.splitext(os.path.basename(a))[0], a) for a in args] or DEFAULT_LISTS
    os.makedirs(OUT, exist_ok=True)
    settings = Settings()
    settings.require_llm_key()

    rollup = ["# Coverage rollup — all lists", ""]
    for name, path in lists:
        if not os.path.isfile(path):
            print(f"SKIP (not found): {path}", file=sys.stderr)
            continue
        urls, contexts = load_inputs([path])
        print(f"[{name}] crawling {len(urls)} URLs ...", file=sys.stderr, flush=True)
        results = await run_urls(urls, settings, contexts=contexts)
        rows = summarize(results)
        title = f"{name} ({len(urls)} URLs)"
        md = coverage_markdown(title, rows)

        stem = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
        with open(f"{OUT}/{stem}.md", "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(f"{OUT}/{stem}.csv", "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(coverage_csv_rows(rows))

        # rollup: just the headline line
        head = md.splitlines()[2] if len(md.splitlines()) > 2 else ""
        rollup.append(f"- **{name}** — {head}")
        print("\n" + md + "\n", flush=True)

    with open(f"{OUT}/ROLLUP.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(rollup) + "\n")
    print("\n".join(rollup), flush=True)
    print(f"\nWrote reports to {OUT}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
