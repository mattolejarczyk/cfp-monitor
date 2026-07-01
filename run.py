#!/usr/bin/env python
"""CLI: analyze a fixed list of conference URLs → structured JSON (feat 1, 13).

Usage:
  python run.py examples/urls.txt                 # read URLs from a file (one per line)
  python run.py https://conf.example.com ...      # or pass URLs directly
  python run.py examples/urls.txt -o results.json # write JSON to a file
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from src.cfp_monitor import run_urls, Settings


def _load_urls(args: list[str]) -> list[str]:
    urls: list[str] = []
    for a in args:
        if os.path.isfile(a):
            with open(a, encoding="utf-8") as f:
                urls += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        else:
            urls.append(a)
    return urls


def main() -> int:
    ap = argparse.ArgumentParser(description="Conference CFP monitor")
    ap.add_argument("inputs", nargs="+", help="URL(s) or a file of URLs (one per line)")
    ap.add_argument("-o", "--output", help="write JSON results here (default: stdout)")
    ap.add_argument("--max-pages", type=int, help="override crawl page budget per site")
    ap.add_argument("--max-depth", type=int, help="override crawl depth per site")
    args = ap.parse_args()

    urls = _load_urls(args.inputs)
    if not urls:
        print("No URLs provided.", file=sys.stderr)
        return 2

    settings = Settings()
    if args.max_pages:
        settings.max_pages = args.max_pages
    if args.max_depth:
        settings.max_depth = args.max_depth

    results = asyncio.run(run_urls(urls, settings))
    payload = [r.model_dump(mode="json") for r in results]
    text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        # brief human summary to stderr
        for r in results:
            status = r.error or r.cfp_status.value
            print(f"{r.start_url}  ->  cfp={r.has_cfp} status={status}", file=sys.stderr)
        print(f"\nWrote {len(results)} result(s) to {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
