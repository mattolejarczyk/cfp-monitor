"""PROPOSE REPLACEMENTS for the dead links in the weekly digest (ACT-24, failure point B3). Read-only: it reads the digest, the database (mode=ro) and the event's own site; it writes a CSV and a
short report for the REVIEWER. Nothing goes to upstream, nothing is written to the data.

    python scripts/propose_replacements.py [--digest <weekly_verify_*.md>] [--out-dir <dir>] [--max-events 60] [--max-minutes 150] [--max-usd 0.30] [--dry-run]

WHY. The weekly digest lists 15 new and 62 backlog dead links; the hand-back to upstream carried a complaint, not an answer. For each event with a dead link this finds the live page on the
event's OWN site (sitemap + menu + home page, the frozen v3.1 page rules) and reads it with the cheap model; a replacement for a call link is PROPOSED only when a deadline with its year is proven
on that page by a verbatim quote (the same code-checked acceptance as the shadow run); a replacement for an event page is PROPOSED only when the live page names the event.
STATUS per link: PROPOSED (live page, proof quote), LEAD (a live page named for the call exists but states no deadline with its year: a person reads it), NONE (the site was read and no page qualifies),
UNREADABLE (home page not reachable or anti-bot host: skipped without touching the network), PAST-EDITION (the event is over: its call page comes down by design, nothing to replace; see ACT-46),
NOT-FOUND (the digest's event name matches no row, so no site to start from).
Reuses scripts/shadow_finder.build_ctx and experiments/finder_reader_test (find_and_read, accept_deadline, choose_main). Own request log and cost cap (default 0.30 USD)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import difflib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor"
CALL_PATH = re.compile(r"call[-_ ]?for|cfp|cfs|speak|abstract|submi|propos|paper|present|nominat|entry|entries|apply", re.I)
AGGREGATORS = ("redcanary.com", "sessionize.com", "cfptime.org", "confs.tech", "linkedin.com", "facebook.com", "eventbrite.com", "openssf.org", "wikicfp.com", "easychair.org")
STOP = {"the", "of", "and", "for", "annual", "international", "conference", "summit", "expo", "exhibition", "congress", "forum", "meeting", "global", "2025", "2026", "2027", "2028"}


def host_of(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


def parse_digest(text: str) -> list[dict]:
    """[{section: 'new'|'backlog', event, url}] from the NEW dead links and Standing backlog sections of a weekly_verify_*.md."""
    out, section = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            low = line.lower()
            section = "new" if "new dead links" in low else ("backlog" if "standing backlog" in low else "")
            continue
        m = re.match(r"- \*\*(.+?)\*\* - (https?://\S+)\s*$", line)
        if section and m:
            out.append({"section": section, "event": m.group(1).strip(), "url": m.group(2).strip()})
    return out


def link_kind(url: str) -> str:
    """'call' when the dead address looks like a call-for-speakers/abstracts/submission page, else 'info'."""
    return "call" if CALL_PATH.search(urlparse(url).path + " " + urlparse(url).netloc.split(".")[0]) else "info"


def locate(event: str, rows: list[dict], cutoff: float = 0.88) -> dict | None:
    """The database row for a digest event name: exact (case-insensitive) first, else a close name; None when nothing is close (no guessing a site)."""
    key = " ".join(event.lower().split())
    exact = [r for r in rows if " ".join((r["name"] or "").lower().split()) == key]
    if exact:
        return sorted(exact, key=lambda r: r.get("start_date") or "", reverse=True)[0]
    best, score = None, 0.0
    for r in rows:
        s = difflib.SequenceMatcher(None, key, " ".join((r["name"] or "").lower().split())).ratio()
        if s > score:
            best, score = r, s
    return best if score >= cutoff else None


def past_edition(row: dict, today: str) -> bool:
    """The event is over: its start date is past, or (no start date) its edition year is. A past event's call page comes down by design."""
    s = (row.get("start_date") or "").strip()
    if s:
        return s < today
    e = str(row.get("edition") or "").strip()
    return bool(e) and e < today[:4]


def home_candidates(row: dict, dead_urls: set[str]) -> list[str]:
    """Where to start on the event's own site: a stored address that is not itself dead, then the site root of a dead address on a non-aggregator host."""
    out = []
    for c in ("main_info_url", "url", "submission_url", "deadline_evidence_url"):
        u = (row.get(c) or "").strip()
        if u.startswith("http") and u not in dead_urls and host_of(u) not in AGGREGATORS and u not in out:
            out.append(u)
    for u in sorted(dead_urls):
        h = host_of(u)
        if h and h not in AGGREGATORS:
            root = f"{urlparse(u).scheme}://{urlparse(u).netloc}/"
            if root not in out:
                out.append(root)
    return out


def names_event(text: str, event: str) -> str:
    """The sentence of `text` that names the event (its distinctive words, at least two or the only one), else ''. Used to prove a replacement EVENT page."""
    words = [w for w in re.findall(r"[a-z0-9]+", event.lower()) if w not in STOP and len(w) > 2]
    if not words:
        return ""
    need = min(2, len(words))
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        low = sent.lower()
        if sum(1 for w in words if re.search(rf"(?<![a-z0-9]){re.escape(w)}", low)) >= need and 20 <= len(sent) <= 400:
            return re.sub(r"\s+", " ", sent).strip()
    return ""


WRONG_KIND = re.compile(r"(?:^|[/_.-])(awards?|prizes?|phd|doctoral|doctorate|degrees?|masters?|msc|bsc|scholarships?|admissions?|undergraduate|postgraduate|graduate-programmes?|tuition)(?:$|[/_.-])", re.I)


def wrong_kind(url: str, event: str) -> str:
    """ACT-42: the proposed address is a page of another KIND (an awards page or a degree-programme page) for an event that is neither. '' when fine, else the word that gave it away.
    The first run proposed a PhD programme page for a conference and an awards page as a call page."""
    m = WRONG_KIND.search(urlparse(url or "").path)
    if m and not re.search(m.group(1)[:5], event or "", re.I):
        return m.group(1).lower()
    return ""


def names_this_event(text: str, quote: str, event: str, url: str, width: int = 350) -> str:
    """ACT-42: the evidence that THIS event, not a sibling, owns the date on this page. A page that lists several events proves nothing for one of them unless the text next to the date names it
    (SANS CDI 2026 got the 19 October deadline of the CTI and OSINT summits from the shared speak-at-a-summit page). Returns the words found (the event's distinctive words within `width`
    characters of the quote, plus the page address), or '' when fewer than 60 percent of them (at least two, or the only one) are there. Pure."""
    words = [w for w in re.findall(r"[a-z0-9]+", (event or "").lower()) if w not in STOP and len(w) > 2 and not w.isdigit()]
    words = list(dict.fromkeys(words))
    if not words:
        return ""
    need = 1 if len(words) == 1 else max(2, -(-len(words) * 6 // 10))
    flat = re.sub(r"\s+", " ", text or "")
    q = re.sub(r"\s+", " ", quote or "").strip()
    at = flat.lower().find(q.lower()[:60]) if q else -1
    window = (flat[max(0, at - width): at + len(q) + width] if at >= 0 else flat[:2 * width]) + " " + urlparse(url or "").path.replace("/", " ").replace("-", " ").replace("_", " ")
    low = window.lower()
    hit = [w for w in words if re.search(rf"(?<![a-z0-9]){re.escape(w)}", low)]
    return ", ".join(hit) if len(hit) >= need else ""


def propose_for_link(link: dict, rec: dict, cache: dict[str, str], event: str, today: str) -> dict:
    """The proposal for ONE dead link from the event's find_and_read record (`rec`) and the page texts it read (`cache`)."""
    kind = link_kind(link["url"])
    base = {"link_kind": kind, "proposed_url": "", "deadline": "", "quote": "", "status": "NONE", "note": ""}
    if rec.get("skipped"):
        return {**base, "status": "UNREADABLE", "note": str(rec["skipped"])}
    pages = rec.get("pages") or []
    if not any(p.get("chars", 0) > 300 for p in pages):
        return {**base, "status": "UNREADABLE", "note": "no page of the site could be read"}
    pick = rec.get("pick") or {}
    if kind == "call":
        if pick.get("pick"):
            pu = next((p for p in pages if p.get("accepted") == pick["pick"] and p.get("rank") != 0), {})
            wk = wrong_kind(pu.get("url", ""), event)
            if wk:
                return {**base, "status": "NONE", "note": f"the page with the date is a '{wk}' page, not this event's call: {pu.get('url', '')}"}
            who = names_this_event(cache.get(pu.get("url", ""), ""), pu.get("quote", ""), event, pu.get("url", ""))
            if not who:                                                   # ACT-42: a date on a page that does not name THIS event next to it is a lead for a person, never a proposal
                return {**base, "status": "LEAD", "proposed_url": pu.get("url", ""), "note": f"a page states {pick['pick']} but nothing next to it names this event (a shared page for several events?): {pu.get('quote', '')[:120]}"}
            return {**base, "status": "PROPOSED", "proposed_url": pu.get("url", ""), "deadline": pick["pick"], "quote": pu.get("quote", ""), "note": (pick.get("why", "") + f"; names the event: {who}").strip("; ")}
        lead = next((p for p in pages if p.get("rank") not in (0, -1) and p.get("chars", 0) > 500 and CALL_PATH.search(urlparse(p.get("url", "")).path)), None)
        if lead and wrong_kind(lead["url"], event):
            lead = None
        if lead:
            return {**base, "status": "LEAD", "proposed_url": lead["url"], "note": "a live page named for the call exists; it states no deadline with its year"}
        return {**base, "note": "the site was read; no live page named for the call and no proven deadline"}
    for p in pages:                                                       # an EVENT page: the home page (or any read page) that names the event
        if p.get("chars", 0) > 300:
            s = names_event(cache.get(p["url"], ""), event)
            if s and not wrong_kind(p["url"], event):
                return {**base, "status": "PROPOSED", "proposed_url": p["url"], "quote": s[:300], "note": "the live page names the event"}
    return {**base, "note": "the site was read; no page names the event"}


def report_md(rows: list[dict], meta: dict) -> str:
    from collections import Counter
    c = Counter(r["status"] for r in rows)
    lines = [f"# Replacement proposals for dead links ({meta['stamp']}) - for the reviewer, nothing is sent", "",
             f"{meta['links']} dead links ({meta['new']} new, {meta['backlog']} backlog) on {meta['events']} events; {meta['read']} events read on their own sites; {meta['minutes']:.0f} minutes; cost {meta['usd']:.4f} USD"
             f"{'; ' + meta['stopped'] if meta['stopped'] else ''}.", "",
             "| " + " | ".join(["PROPOSED", "LEAD", "NONE", "UNREADABLE", "PAST-EDITION", "NOT-FOUND"]) + " |", "|---|---|---|---|---|---|",
             "| " + " | ".join(str(c.get(k, 0)) for k in ["PROPOSED", "LEAD", "NONE", "UNREADABLE", "PAST-EDITION", "NOT-FOUND"]) + " |", "",
             "PROPOSED = a live page on the event's own site with a proof quote (a deadline with its year for a call link; the event named for an event link). A person confirms before upstream is asked.", ""]
    for r in [x for x in rows if x["status"] in ("PROPOSED", "LEAD")]:
        lines.append(f"- **{r['event']}** ({r['section']}, {r['link_kind']}): dead {r['dead_url']}  ->  {r['status']} {r['proposed_url']}" + (f"  deadline {r['deadline']} (ours {r['ours_deadline'] or 'blank'})" if r["deadline"] else ""))
        if r["quote"]:
            lines.append(f"  - \"{r['quote'][:220]}\"")
    return "\n".join(lines)


def write_outputs(out: list[dict], meta: dict, stem: Path) -> None:
    cols = ["section", "event", "event_id", "dead_url", "link_kind", "status", "proposed_url", "deadline", "ours_deadline", "quote", "note"]
    with open(f"{stem}.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    Path(f"{stem}.md").write_text(report_md(out, meta), encoding="utf-8")
    Path(f"{stem}.json").write_text(json.dumps({"meta": meta, "rows": out}, indent=1, ensure_ascii=False), encoding="utf-8")


async def run(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    digest = Path(a.digest) if a.digest else max((DATA_ROOT / "runs_out").glob("weekly_verify_*.md"), key=lambda p: p.stat().st_mtime)
    links = parse_digest(digest.read_text(encoding="utf-8"))
    db = DATA_ROOT / "cfp_monitor.db"
    con = sqlite3.connect(f"file:{str(db).replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select event_id, name, url, main_info_url, submission_url, deadline_evidence_url, deadline, start_date, edition, status from grounding_facts")]
    con.close()
    by_event: dict[str, list[dict]] = {}
    for l in links:
        by_event.setdefault(l["event"], []).append(l)
    print(f"digest {digest.name}: {len(links)} dead links on {len(by_event)} events", flush=True)
    plan, out = [], []
    for event, ls in by_event.items():
        row = locate(event, rows)
        if row is None:
            out += [{**l, "event_id": "", "ours_deadline": "", "link_kind": link_kind(l["url"]), "dead_url": l["url"], "proposed_url": "", "deadline": "", "quote": "", "status": "NOT-FOUND",
                     "note": "no database row with this name"} for l in ls]
        elif past_edition(row, a.today):
            out += [{**l, "event_id": row["event_id"], "ours_deadline": row.get("deadline") or "", "link_kind": link_kind(l["url"]), "dead_url": l["url"], "proposed_url": "", "deadline": "", "quote": "",
                     "status": "PAST-EDITION", "note": f"the event started {row.get('start_date') or row.get('edition')}: a past edition's call page comes down by design"} for l in ls]
        else:
            plan.append((event, row, ls))
    plan = plan[:a.max_events]
    print(f"{len(plan)} events in scope ({len(out)} links already classified without reading)", flush=True)
    if a.dry_run:
        for event, row, ls in plan:
            print(f"  {event[:52]:52} {len(ls)} link(s)  start from {home_candidates(row, {l['url'] for l in ls})[:1]}")
        return 0
    from experiments.finder_reader_test import run as F
    from scripts.shadow_finder import build_ctx
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(a.out_dir) if a.out_dir else DATA_ROOT / "runs_out" / "shadow"
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = build_ctx(out_dir / f"propose_llm_log_{stamp}.jsonl", a.max_usd)
    R, _f = ctx.R, ctx._f
    t0, stopped, read = time.time(), "", 0
    for i, (event, row, ls) in enumerate(plan, 1):
        if (time.time() - t0) / 60 > a.max_minutes:
            stopped = f"stopped at the {a.max_minutes}-minute limit"
            break
        if R.spent()[1] >= a.max_usd:
            stopped = f"stopped at the {a.max_usd} USD cap"
            break
        homes = home_candidates(row, {l["url"] for l in ls})
        cache: dict[str, str] = {}
        rec: dict = {"skipped": "no address to start from"}
        for home in homes[:2]:                                            # the stored address, then the site root
            ev = {"event": event, "home": home, "hosts": sorted({host_of(u) for u in homes + [home] if host_of(u) and host_of(u) not in AGGREGATORS}), "control": "", "gold": ""}
            try:
                rec = await F.find_and_read(ev, ctx, 8, "C", a.today, cache, say=lambda *x, **k: None)
            except SystemExit as e:                                       # the request log's budget guard
                stopped = f"stopped: {e}"
                break
            except Exception as e:                                        # noqa: BLE001  one bad site must not end the run
                rec = {"skipped": f"{type(e).__name__}: {e}"}
            if not rec.get("skipped") and any(p.get("chars", 0) > 300 for p in rec.get("pages") or []):
                break
        if stopped.startswith("stopped:"):
            break
        read += 1
        for l in ls:
            pr = propose_for_link(l, rec, cache, event, a.today)
            out.append({**l, "event_id": row["event_id"], "ours_deadline": row.get("deadline") or "", "dead_url": l["url"], **pr})
        got = sorted({o["status"] for o in out[-len(ls):]})
        print(f"  [{i}/{len(plan)}] {event[:50]:50} {','.join(got)}", flush=True)
        write_outputs(out, {"stamp": stamp, "links": len(links), "new": sum(1 for l in links if l["section"] == "new"), "backlog": sum(1 for l in links if l["section"] == "backlog"),
                            "events": len(by_event), "read": read, "minutes": (time.time() - t0) / 60, "usd": R.spent()[1], "stopped": "in progress"}, out_dir / f"replacement_proposals_{stamp}")   # partial results survive a kill
    try:
        await _f.close_fallback_browser()
    except Exception:                                                     # noqa: BLE001
        pass
    meta = {"stamp": stamp, "links": len(links), "new": sum(1 for l in links if l["section"] == "new"), "backlog": sum(1 for l in links if l["section"] == "backlog"), "events": len(by_event),
            "read": read, "minutes": (time.time() - t0) / 60, "usd": R.spent()[1], "stopped": stopped}
    stem = out_dir / f"replacement_proposals_{stamp}"
    write_outputs(out, meta, stem)
    from collections import Counter
    print(f"PROPOSALS: {dict(Counter(o['status'] for o in out))}; {meta['minutes']:.0f} min, {meta['usd']:.3f} USD{'; ' + stopped if stopped else ''} -> {stem}.csv")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--digest", help="a weekly_verify_*.md (default: the newest in runs_out)")
    ap.add_argument("--out-dir", help="where the CSV, report and request log go (default runs_out/shadow; use a scratch folder for a rehearsal)")
    ap.add_argument("--max-events", type=int, default=60)
    ap.add_argument("--max-minutes", type=float, default=150)
    ap.add_argument("--max-usd", type=float, default=0.30)
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="classify and list the events it would read; no network, no model")
    a = ap.parse_args()
    return asyncio.run(run(a))


if __name__ == "__main__":
    raise SystemExit(main())
