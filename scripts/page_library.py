"""Offline PAGE LIBRARY: fetch each planned page ONCE, keep its text, and let every later step read the saved copy.

    python scripts/page_library.py --build [--limit N] [--only HOST ...] [--refresh-older-than DAYS]
    python scripts/page_library.py --report

WHY. Discovery (sitemap + menu + the v3.1 priority rules) picks the pages worth reading, 364 across 70 sites. Reading them with a browser every time a
question changes (a new prompt, a different model, a re-score) is slow, anti-bot sites block repeats, and pages change between runs so results cannot be
compared. The library fetches a page once through the repo's own renderer (fetch._render_with_consent, real Chrome over CDP when CFP_CDP_URL is set),
stores text, anchors, a sha256 and a timestamp, and keeps older versions when a page changes. Models and rules then run on the saved text.

Reuses: experiments/sitemap_discovery (rules_v31.plan over site_inventory.db) and src/cfp_monitor/fetch.py. Writes only page_library/page_library.db (git-ignored).
Resumable: a page already stored is skipped unless --refresh-older-than. Hosts are interleaved so no site is hit twice in a row; 2 s between requests.
Nothing here touches the database of conferences, the deliveries or the customer sheets.
"""
import argparse, asyncio, hashlib, importlib.util, json, os, sqlite3, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / "page_library"
LIB_DB = LIB_DIR / "page_library.db"
INVENTORY = ROOT / "experiments" / "sitemap_discovery" / "site_inventory.db"
SEED_FILES = {
    "crawl_pages": ROOT / "experiments" / "sitemap_discovery" / "crawl_pages.json",
    "audit_pages": ROOT / "experiments" / "purpose_audit" / "audit_pages.json",
    "holdout_pages": ROOT / "experiments" / "heading_reader" / "holdout_pages.json",
}
BLOCK_MARKERS = ("incapsula", "request unsuccessful", "access denied", "just a moment", "attention required",
                 "pardon our interruption", "enable javascript and cookies", "verify you are human")
PAGE_TIMEOUT_S = 90
PAUSE_S = 2.0

SCHEMA = """
create table if not exists pages (
  url text primary key, host text, tier text, via text, first_fetched_at text, last_fetched_at text,
  http_status integer, chars integer, sha256 text, text text, anchors text, soft404 text, blocked integer default 0, error text, fetches integer default 0);
create table if not exists page_versions (
  url text, fetched_at text, sha256 text, chars integer, text text);
create index if not exists ix_pages_host on pages(host);
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def is_block_page(text):
    t = (text or "").strip().lower()
    return bool(t) and len(t) < 600 and any(m in t for m in BLOCK_MARKERS)


def flags(text, soft404_fn=None):
    """{'blocked': bool, 'soft404': str, 'usable': bool}. A page is usable when it has real text and is neither a block page nor a soft 404."""
    blocked = is_block_page(text)
    soft = (soft404_fn(text) if soft404_fn else "") if text else "empty body"
    return {"blocked": blocked, "soft404": soft or "", "usable": bool(text) and not blocked and not soft}


def connect(path=LIB_DB):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=60)
    db.executescript(SCHEMA)
    return db


def upsert_page(db, rec):
    """Store a fetched page. Returns 'new', 'unchanged' or 'changed'. An older text is kept in page_versions when the page changes."""
    row = db.execute("select sha256, text, fetches, first_fetched_at from pages where url=?", (rec["url"],)).fetchone()
    h = sha(rec.get("text"))
    ts = rec.get("fetched_at") or now()
    outcome = "new"
    if row:
        outcome = "unchanged" if row[0] == h else "changed"
        if outcome == "changed" and row[1]:
            db.execute("insert into page_versions values (?,?,?,?,?)", (rec["url"], ts, row[0], len(row[1]), row[1]))
    db.execute(
        "insert into pages (url,host,tier,via,first_fetched_at,last_fetched_at,http_status,chars,sha256,text,anchors,soft404,blocked,error,fetches) "
        "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1) on conflict(url) do update set host=excluded.host, tier=excluded.tier, via=excluded.via, "
        "last_fetched_at=excluded.last_fetched_at, http_status=excluded.http_status, chars=excluded.chars, sha256=excluded.sha256, text=excluded.text, "
        "anchors=excluded.anchors, soft404=excluded.soft404, blocked=excluded.blocked, error=excluded.error, fetches=pages.fetches+1",
        (rec["url"], rec.get("host", ""), rec.get("tier", ""), rec.get("via", ""), row[3] if row else ts, ts, rec.get("http_status"),
         len(rec.get("text") or ""), h, rec.get("text") or "", json.dumps(rec.get("anchors") or []), rec.get("soft404", ""),
         1 if rec.get("blocked") else 0, rec.get("error", "")))
    db.commit()
    return outcome


def load_text(url, path=LIB_DB):
    """The saved text of a page (what every reader should use); '' if the library has no usable copy."""
    db = connect(path)
    row = db.execute("select text from pages where url=?", (url,)).fetchone()
    db.close()
    return row[0] if row and row[0] else ""


def interleave(by_host):
    """Round-robin the per-host lists (each in plan order) so consecutive requests go to different hosts."""
    queues = {h: list(v) for h, v in by_host.items()}
    out = []
    while any(queues.values()):
        for h in sorted(queues):
            if queues[h]:
                out.append(queues[h].pop(0))
    return out


def plan_pages(only=None):
    """[(host, url, tier)] for every planned page of every inventory site, interleaved across hosts."""
    sys.path.insert(0, str(ROOT / "experiments" / "sitemap_discovery"))
    import rules_v31 as r31
    inv = sqlite3.connect(str(INVENTORY), timeout=60)
    by_host = {}
    for (host,) in inv.execute("select host from site_profile order by host"):
        if only and host not in only:
            continue
        maps = [u for (u,) in inv.execute("select url from site_pages where host=? and source='map'", (host,))]
        menu = {u: l for u, l in inv.execute("select url, label from site_pages where host=? and source='menu'", (host,))}
        plan = r31.plan(list(dict.fromkeys(maps + list(menu))), {u: l for u, l in menu.items() if l})
        if plan:
            by_host[host] = [(host, u, t) for u, t in plan]
    return interleave(by_host)


def seed_from_caches(db, urls):
    """Import pages already rendered by earlier experiments, for planned URLs only, so they are not fetched twice. Marked via='seed:<file>'."""
    n = 0
    for name, path in SEED_FILES.items():
        if not path.exists():
            continue
        stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = json.loads(path.read_text(encoding="utf-8"))
        for u, v in data.items():
            text = (v or {}).get("text") or ""
            if u in urls and text and not db.execute("select 1 from pages where url=?", (u,)).fetchone():
                f = flags(text)
                upsert_page(db, {"url": u, "host": urls[u][0], "tier": urls[u][1], "via": f"seed:{name}", "text": text, "fetched_at": stamp,
                                 "anchors": (v or {}).get("anchors") or [], "soft404": f["soft404"], "blocked": f["blocked"]})
                n += 1
    return n


class _Q:
    def log(self, *a, **k):
        pass


async def build(args):
    from src.cfp_monitor import fetch as _f
    from src.cfp_monitor.config import Settings
    spec = importlib.util.spec_from_file_location("cu", ROOT / "scripts" / "check_urls_against_site.py")
    cu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cu)
    settings = Settings()
    db = connect()
    plan = plan_pages(set(args.only) if args.only else None)
    urls = {u: (h, t) for h, u, t in plan}
    print(f"{len(plan)} planned pages on {len({h for h, _, _ in plan})} sites; CDP: {getattr(settings, 'cdp_url', None) or 'not set'}", flush=True)
    print("seeded from earlier caches:", seed_from_caches(db, urls), flush=True)
    cutoff = None
    if args.refresh_older_than is not None:
        cutoff = time.time() - args.refresh_older_than * 86400
    done = fetched = 0
    for host, url, tier in plan:
        row = db.execute("select last_fetched_at, chars from pages where url=?", (url,)).fetchone()
        if row and row[1]:
            if cutoff is None or datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() > cutoff:
                done += 1
                continue
        if args.limit is not None and fetched >= args.limit:
            break
        rec = {"url": url, "host": host, "tier": tier, "via": "render"}
        try:
            html, anchors, status, body, used_cdp = await asyncio.wait_for(_f._render_with_consent(url, settings, _Q(), prefer_cdp=True), PAGE_TIMEOUT_S)
            body = body or ""
            f = flags(body, cu.looks_soft_404)
            rec.update(text=body, http_status=status, soft404=f["soft404"], blocked=f["blocked"], via="cdp" if used_cdp else "render",
                       anchors=[[(a.get("href") or ""), (a.get("text") or "")[:80]] for a in (anchors or [])][:400])
        except Exception as e:                                              # noqa: BLE001
            rec.update(text="", error=type(e).__name__)
        outcome = upsert_page(db, rec)
        fetched += 1
        print(f"[{done + fetched}/{len(plan)}] {outcome:<9} {len(rec.get('text') or ''):>6} chars  {rec.get('error') or rec.get('soft404') or ('BLOCKED' if rec.get('blocked') else 'ok'):<28} {url[:80]}", flush=True)
        await asyncio.sleep(PAUSE_S)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                       # noqa: BLE001
        pass
    print("DONE", flush=True)


def report():
    db = connect()
    rows = db.execute("select url, host, chars, soft404, blocked, error, via from pages").fetchall()
    tot = len(rows)
    ok = [r for r in rows if r[2] and not r[3] and not r[4] and not r[5]]
    print(f"{tot} pages stored; usable {len(ok)}; soft404/thin {sum(1 for r in rows if r[3])}; blocked {sum(1 for r in rows if r[4])}; errors {sum(1 for r in rows if r[5])}; empty {sum(1 for r in rows if not r[2])}")
    print("by source:", dict(db.execute("select substr(via,1,6), count(*) from pages group by 1").fetchall()))
    print("sites with at least one usable page:", len({r[1] for r in ok}), "of", len({r[1] for r in rows}))
    print("page versions kept:", db.execute("select count(*) from page_versions").fetchone()[0])
    bad = {}
    for r in rows:
        if r not in ok:
            bad.setdefault(r[1], []).append(r[3] or ("blocked" if r[4] else r[5] or "empty"))
    for h, v in sorted(bad.items(), key=lambda x: -len(x[1]))[:12]:
        print(f"  problem pages at {h}: {len(v)}  e.g. {v[0][:60]}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refresh-older-than", type=float, dest="refresh_older_than")
    a = ap.parse_args()
    if a.build:
        asyncio.run(build(a))
    if a.report or not a.build:
        report()
