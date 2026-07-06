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

    banner = (f"_Batch settings: max_pages={settings.max_pages}, "
              f"max_extract_pages={settings.max_extract_pages}, "
              f"per_site_timeout={settings.per_site_timeout_s}s, "
              f"CDP={'on' if settings.cdp_url else 'off'}._")
    rollup = ["# Coverage rollup — all lists", "", banner, ""]
    for name, path in lists:
        if not os.path.isfile(path):
            print(f"SKIP (not found): {path}", file=sys.stderr)
            continue
        urls, contexts = load_inputs([path])
        print(f"[{name}] crawling {len(urls)} URLs ...", file=sys.stderr, flush=True)
        results = await run_urls(urls, settings, contexts=contexts)
        rows = summarize(results)
        title = f"{name} ({len(urls)} URLs)"
        body = coverage_markdown(title, rows)
        head, _, rest = body.partition("\n")      # insert settings banner just under the H1
        md = f"{head}\n\n{banner}\n{rest}"

        stem = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
        with open(f"{OUT}/{stem}.md", "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(f"{OUT}/{stem}.csv", "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(coverage_csv_rows(rows))

        # rollup: the one headline line (worked/failed counts)
        headline = next((ln for ln in md.splitlines() if ln.startswith("**") and "URLs" in ln), "")
        rollup.append(f"- **{name}** — {headline}")
        print("\n" + md + "\n", flush=True)

    with open(f"{OUT}/ROLLUP.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(rollup) + "\n")
    print("\n".join(rollup), flush=True)
    print(f"\nWrote reports to {OUT}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
