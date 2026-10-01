"""Stage 2: render each customer-market site's HOMEPAGE once and record its internal links with the zone they sit in
(menu / header / footer / body). One page per site; no deeper crawling; no AI.

Uses the repo's own renderer (fetch._render_with_consent via prefer_cdp) - the same call trace_quote_to_page.py uses. Hard anti-bot
hosts (fetch._force_fallback_domain) are skipped without touching the network, per the existing IP-protection rule.
Stores rows in site_inventory.db (site_pages, source='menu') and homepage status in site_menu_status. Resumable.
"""
import asyncio, importlib.util, re, sqlite3, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import fetch as _f                # noqa: E402
from src.cfp_monitor import sitewalk                   # noqa: E402
from src.cfp_monitor.config import Settings            # noqa: E402

DBF = HERE / "site_inventory.db"
VOID = {"a_", "br", "hr", "img", "input", "meta", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
NAVWORDS = re.compile(r"(^|[\s_-])(nav|navbar|navigation|menu|mainmenu|main-menu|primary)($|[\s_-])", re.I)


class Zones(HTMLParser):
    """Collects (href, text, zone) for every <a>. Zone = footer > nav/header/menu > body, from the ancestors at that point."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.links, self._cur = [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in VOID and tag != "a":
            self.stack.append((tag, (a.get("class") or "") + " " + (a.get("id") or ""), (a.get("role") or "").lower()))
        if tag == "a" and a.get("href"):
            tags = [t for t, _c, _r in self.stack]
            ids = [c for _t, c, _r in self.stack]
            roles = [r for _t, _c, r in self.stack]
            if "footer" in tags or any(re.search(r"footer", c, re.I) for c in ids):
                zone = "footer"
            elif "nav" in tags or "navigation" in roles or any(NAVWORDS.search(c) for c in ids):
                zone = "menu"
            elif "header" in tags:
                zone = "header"
            else:
                zone = "body"
            self._cur = [a["href"], "", zone]
            self.links.append(self._cur)

    def handle_endtag(self, tag):
        if tag == "a":
            self._cur = None
        elif self.stack:
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[1] += data


class _Quiet:
    def log(self, *a, **k):
        pass


async def main():
    settings = Settings()
    db = sqlite3.connect(DBF, timeout=120)      # wait rather than crash if another pass holds the file
    db.execute("create table if not exists site_menu_status(host text primary key, homepage_chars int, links int, menu_links int, note text, fetched_at text)")
    hosts = [(h, o) for h, o in db.execute("select host, origin from site_profile order by host")]
    print(f"{len(hosts)} homepages", flush=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for n, (host, origin) in enumerate(hosts, 1):
        if db.execute("select 1 from site_menu_status where host=?", (host,)).fetchone():
            continue
        note, html, body = "", "", ""
        if _f._force_fallback_domain(origin) and not _f.cdp_reachable(getattr(settings, "cdp_url", None)):
            note = "skipped: hard anti-bot site (IP protection)"
        else:
            try:
                html, _anchors, _st, body, _c = await _f._render_with_consent(origin, settings, _Quiet(), prefer_cdp=True)
            except Exception as e:                                        # noqa: BLE001
                note = f"render failed: {type(e).__name__}"
        z = Zones()
        if html:
            try:
                z.feed(html)
            except Exception:                                              # noqa: BLE001
                note = note or "html parse error"
        seen, nav = set(), 0
        db.execute("delete from site_pages where host=? and source='menu'", (host,))
        for href, text, zone in z.links:
            href = (href or "").strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            url = urljoin(origin + "/", href).split("#")[0]
            if not sitewalk.same_site(url, origin) or url in seen:
                continue
            seen.add(url)
            nav += zone in ("menu", "header")
            db.execute("insert or ignore into site_pages(host,url,source,in_menu,menu_zone,first_seen) values(?,?,?,?,?,?)",
                       (host, url, "menu", int(zone in ("menu", "header")), zone, now))
        db.execute("insert or replace into site_menu_status values(?,?,?,?,?,?)",
                   (host, len(body or ""), len(seen), nav, note, now))
        db.commit()
        print(f"[{n}/{len(hosts)}] {host[:34]:<34} home={len(body or ''):>6}ch links={len(seen):>4} menu+header={nav:>3} {note}", flush=True)
        await asyncio.sleep(2)
    try:
        await _f.close_fallback_browser()
    except Exception:                                                      # noqa: BLE001
        pass
    print("DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
