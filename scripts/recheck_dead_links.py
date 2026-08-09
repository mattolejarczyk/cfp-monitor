"""Second-opinion check on links our fast pass called dead.

    python scripts/recheck_dead_links.py --db cfp_monitor.db [--apply]

A 404 from a plain HTTP request is not conclusive: plenty of sites answer non-browser
traffic with an error page while serving the same URL fine to a real browser. Before we hand
"your link is dead" back to the discovery layer, re-check each one with a real browser so we
distinguish TRULY DEAD from BLOCKED-TO-SCRIPTS. Only the former is evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.storage import Store          # noqa: E402


async def browser_check(urls: list[str]) -> dict[str, tuple[str, int, int]]:
    """{url: (verdict, http_status, body_chars)} using a real headless browser."""
    from playwright.async_api import async_playwright

    out: dict[str, tuple[str, int, int]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
        for url in urls:
            page = await ctx.new_page()
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                status = resp.status if resp else 0
                body = await page.inner_text("body")
                chars = len(body.strip())
                # A soft 404 returns 200 with an error page; judge on content as well.
                low = body.lower()[:4000]
                soft = any(s in low for s in ("404", "page not found", "cannot be found",
                                              "doesn't exist", "does not exist"))
                if status in (404, 410) or (soft and chars < 2500):
                    verdict = "dead"
                elif status >= 400:
                    verdict = f"http {status}"
                elif chars < 200:
                    verdict = "empty"
                else:
                    verdict = "ALIVE"
                out[url] = (verdict, status, chars)
            except Exception as e:
                out[url] = (f"error: {type(e).__name__}", 0, 0)
            finally:
                await page.close()
        await browser.close()
    return out


def recheck_csv(path: str) -> int:
    """Same second opinion, but on a delivery CSV that has not been imported yet.

    Added 2026-08-06. Without this the browser check was only reachable once a
    delivery was in the database, so anything working at the CSV stage had no way
    to tell TRULY DEAD from BLOCKED-TO-SCRIPTS - and a parallel, weaker checker got
    built instead. Same browser_check(), just a different source of URLs.
    """
    import csv as _csv
    from src.cfp_monitor.verify import link_status

    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(_csv.DictReader(fh))

    # "SUBMISSION URL" added 2026-08-08. It is the link the CUSTOMER clicks, and it is a
    # distinct column from CFP_SUBMISSION_URL - 22 of 406 rows in the 8-market delivery had
    # a SUBMISSION URL that appeared nowhere else, so the CSV mode was silently skipping the
    # one link whose death the customer would actually notice.
    columns = ["SUBMISSION URL", "DEADLINE_EVIDENCE_URL", "VENUE_EVIDENCE_URL",
               "CFP_SUBMISSION_URL", "MAIN_INFO_URL"]
    suspects: dict[str, list[str]] = {}
    seen: dict[str, int | None] = {}
    for r in rows:
        for c in columns:
            u = (r.get(c) or "").strip()
            if not u.startswith("http"):
                continue
            if u not in seen:
                seen[u], _ = link_status(u)
            if seen[u] in (404, 410):
                suspects.setdefault(u, []).append(f'{(r.get("CONFERENCE") or "")[:36]} [{c}]')

    print(f"pass 1 checked {len(seen)} url(s); {len(suspects)} returned 404/410\n")
    if not suspects:
        print("Nothing for the browser to re-check.")
        return 0

    results = asyncio.run(browser_check(list(suspects)))
    dead, false_404 = [], []
    for u, where in suspects.items():
        verdict, status, chars = results.get(u, ("no result", 0, 0))
        (dead if verdict == "dead" else false_404).append((u, verdict, where))
        print(f"  {verdict[:12]:<13} {u[:66]}")
        for w in where:
            print(f"                {w}")

    print(f"\ntruly dead: {len(dead)}   |   reachable in a browser: {len(false_404)}")
    if false_404:
        print("\nThese were FALSE 404s - the link works, our plain HTTP request was blocked.")
        print("Withdrawing their citations would have been wrong (contract 5.2).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-check 'dead' links with a real browser.")
    ap.add_argument("--db", default="cfp_monitor.db")
    ap.add_argument("--csv", help="re-check a delivery CSV instead of the database")
    ap.add_argument("--apply", action="store_true", help="downgrade false 404s to not_found")
    a = ap.parse_args()

    if a.csv:
        return recheck_csv(a.csv)

    store = Store(a.db)
    rows = [dict(r) for r in store.db.execute(
        "SELECT * FROM grounding_facts WHERE verify_state='contradicted'"
        " AND verify_detail LIKE '%404%'")]
    print("re-checking {} link(s) our fast pass called dead\n".format(len(rows)))
    urls = [r["submission_url"] for r in rows if r["submission_url"]]
    results = asyncio.run(browser_check(urls))

    alive, dead = [], []
    for r in rows:
        verdict, status, chars = results.get(r["submission_url"], ("no url", 0, 0))
        (alive if verdict == "ALIVE" else dead).append((r, verdict, status, chars))
        print("  {:<10} {:<38} {}".format(verdict[:10], (r["name"] or "")[:36],
                                          (r["submission_url"] or "")[:58]))

    print("\ntruly dead: {}   |   actually reachable in a browser: {}".format(
        len(dead), len(alive)))
    if alive:
        print("\nThese were FALSE 404s -- the link works, our plain HTTP request was blocked.")
        print("Calling them dead to the discovery layer would have been wrong.")
    if a.apply and alive:
        for r, *_ in alive:
            store.db.execute(
                "UPDATE grounding_facts SET verify_state='not_found', verify_detail=?"
                " WHERE event_id=?",
                ("[L1b] link is reachable in a real browser; plain HTTP was blocked",
                 r["event_id"]))
        store.db.commit()
        print("\nDowngraded {} false 404(s) to not_found.".format(len(alive)))
    elif alive:
        print("\nRe-run with --apply to correct them.")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
