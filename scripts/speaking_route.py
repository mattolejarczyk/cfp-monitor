"""HOW DOES A COMPANY GET A SPEAKING SLOT AT THIS EVENT, AND MUST IT PAY? (2026-10-19, operator direction; contract R19.1, R19.2, R21)

    python scripts/speaking_route.py [--db DB] [--apply] [--limit 40] [--max-minutes 25] [--concurrency 5] [--stale-days 56] [--event-id ID ...] [--out-dir DIR]

WHY. SPONSOR_REQUIRED came to mean "sponsorship packages exist" (211 of 220 approved rows say Yes) because the question upstream is asked counts any event that "states or implies" that exhibiting or sponsoring costs money.
The customer's question is about the ROUTE to a speaking slot. A cheap model answers it well when it is shown several pages of the event's own site together and asked the right thing
(experiments/sponsor_reader/RESULT.md, round 2: about 60 percent of events get a clear, quoted answer at about 0.002 USD each; 0 of 36 events said vendors MUST sponsor to speak).

WHAT IT DOES. For each event in the two customer markets that has no route yet (or whose route is older than --stale-days; an UNCLEAR one is retried after a shorter time): the home page, the sponsorship page upstream
cited, up to 3 sponsor-type pages and up to 3 call-for-speakers pages, picked from the site's sitemap and menu by URL and link-text words, are read (real Chrome when it is running, then plain), and ONE call to the cheap
model gets all of them, labelled by kind, with four questions: is there a public call anyone can submit to; are speaking slots included in or sold with sponsor or exhibitor packages; does a page say vendors MUST sponsor to
speak; one plain sentence. CODE then (1) checks every quote is word for word on the pages, (2) checks the quote SAYS what the answer claims (a regular expression per claim), (3) drops a call whose quote is dated to an
earlier year than the edition, and (4) derives the route. The model never decides the label.
ROUTES: MUST_SPONSOR (a verified quote says vendors must sponsor, exhibit or pay to speak, or that speaking is reserved for sponsors), OPEN_CALL, OPEN_CALL_AND_PAID_SLOTS, PAID_SLOTS_NO_CALL_SEEN (slots come with sponsor
packages and no public call was found: NOT proof that none exists), INVITE_ONLY (a verified quote says speakers are invited or chosen by the organizer), UNCLEAR (Unknown is a complete answer, R19.2).
WRITES. Only the table `speaking_route` (created if missing) in the database, with who established it and when (R21.2: provenance lives in our store). It never touches a delivery file, a pinned value, or any upstream-owned
column (R21.1). Without --apply it only reports. READS the network (2 s apart per site, no hard anti-bot hosts) and calls the cheap model (deepseek-chat via OpenRouter, the extraction model of docs/design/model-costs.md).
Advisory: any fault prints a line and exits 0; it can never fail a weekly job. A time cap (--max-minutes) stops it between events."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
SEED_DIR = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\market_sheets")
ROUTES = ("MUST_SPONSOR", "OPEN_CALL", "OPEN_CALL_AND_PAID_SLOTS", "PAID_SLOTS_NO_CALL_SEEN", "INVITE_ONLY", "UNCLEAR")
DECIDED = ROUTES[:-1]
MODEL_NAME = "openrouter/deepseek/deepseek-chat"
PRICE_IN, PRICE_OUT = 0.27 / 1e6, 1.10 / 1e6                      # an ESTIMATE (docs/design/model-costs.md): used only to print the cost of a run

SYSTEM = """You help a company that wants to SPEAK at a conference. You are given the text of several pages from the conference's own website, each labelled with its kind (home, call = a call-for-speakers page,
sponsor = a sponsorship or exhibitor page, cited-sponsor = the sponsorship page a researcher cited). Use ONLY this text. The edition we care about is stated in the first line (CONFERENCE and EDITION). A call, deadline or
page that is clearly for a DIFFERENT year or edition (for example "Due July 30, 2021", or a page about the 2026 call when the edition is 2027) does not count: treat that as "unclear". Answer four questions. For each, quote
the exact words (copy them exactly; never reword) or leave the quote empty.

1. open_call: "yes" if the pages describe a public call for speakers, papers, abstracts or proposals that people can submit to (a form, a link, instructions or a deadline), whether or not the person is a vendor;
   "no" ONLY if a page says speakers are by invitation only, chosen by the organizer or its analysts, or that there is no public call (quote that sentence); otherwise "unclear".
2. paid_slots: "yes" if the pages say speaking, presenting, a keynote, a panel, a session or a speaking slot is INCLUDED in, or can be BOUGHT as part of, a sponsorship or exhibitor package; "no" if they say it is not; otherwise "unclear".
   A package that only lists a logo, a booth, passes or branding is "no".
3. must_pay: "yes" ONLY if a page says that companies or vendors MUST sponsor, exhibit or pay to speak, or that speaking is reserved for sponsors; "no" if a page says sponsoring does not buy or guarantee a speaking slot, or that speakers are chosen
   independently of sponsorship; otherwise "unclear".
4. summary: one plain sentence saying how a company gets a speaking slot here.

Return ONLY this JSON:
{"open_call": "yes|no|unclear", "open_call_quote": "", "paid_slots": "yes|no|unclear", "paid_slots_quote": "", "must_pay": "yes|no|unclear", "must_pay_quote": "", "summary": ""}"""

# A quote must SAY what the answer claims, in words the code can check (a model that over-reads a weak sentence is caught here, not trusted).
SAYS = {
    ("open_call", "yes"): re.compile(r"call for|call-for|submit|submission|propos|suggestion|abstract|apply|application|nominat|\bcfp\b|become a speaker|propose a speaker|register your interest|speaker form|interested in (speaking|presenting)|e-?mail .{0,60}(speaker|present|synopsis)", re.I),
    ("open_call", "no"): re.compile(r"invit|curated|selected by the|chosen by|by the (organi[sz]|program|advisory|analyst)|analyst|no (public )?call|not (accept|open)", re.I),
    ("paid_slots", "yes"): re.compile(r"speak|present|keynote|panel|session|stage|slot|moderat|fireside|spotlight", re.I),
    ("must_pay", "yes"): re.compile(r"must|required|requires|only|reserved|exclusive|solely|need to", re.I),
}
NOT_A_SPEAKERS_CALL = re.compile(r"program committee|review board|reviewers?|volunteer", re.I)
SPEAKER_WORDS = re.compile(r"speaker|paper|abstract|present|talk|briefing", re.I)

SPONSOR_WORDS = (("sponsor", 4), ("prospectus", 4), ("partner", 3), ("exhibit", 2), ("packages", 3), ("package", 2), ("get-involved", 2), ("get involved", 2), ("become-a", 2), ("why-", 1),
                 ("faq", 2), ("brochure", 3), ("media-kit", 3), ("advertis", 2))
CALL_WORDS = (("call-for", 4), ("call for", 4), ("cfp", 4), ("become-a-speaker", 4), ("speaker", 3), ("speak", 2), ("submit", 2), ("abstract", 3), ("proposal", 3), ("propose", 3), ("suggest", 2),
              ("paper", 2), ("present", 1), ("nominat", 1), ("apply", 1))
AVOID = re.compile(r"(privacy|cookie|terms|login|sign-?in|register|ticket|news|blog|press|past-|previous|archive|gallery|photo|video|career|jobs|contact|sitemap|\.pdf$|\.jpg$|\.png$|\.xml$|wp-json|/tag/|/category/|/author/)", re.I)


# ------------------------------------------------------------------ pure parts (tested offline)
def host(u: str) -> str:
    return urlparse(u).netloc.lower().removeprefix("www.") if u and u.startswith("http") else ""


def clean(s: str) -> str:
    """The page's own characters, tidied for display: no-break spaces and the mojibake 'A-circumflex' a wrong decode leaves behind become plain spaces."""
    return re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ").replace("\u00c2", " ")).strip()


def norm(s: str) -> str:
    return clean(s).lower()


def quote_on_pages(quote: str, pages: list[dict]) -> bool:
    q = norm(quote)
    return bool(q) and any(q in norm(p["text"]) for p in pages)


def _score(url: str, label: str, words) -> int:
    t = (urlparse(url).path + " " + (label or "")).lower()
    return sum(w for k, w in words if k in t)


def pick(urls: list[str], labels: dict[str, str], words, exclude: set[str], k: int) -> list[str]:
    seen, ranked = {x.rstrip("/").lower() for x in exclude}, []
    for u in urls:
        key = u.rstrip("/").lower()
        if key in seen or AVOID.search(urlparse(u).path):
            continue
        seen.add(key)
        s = _score(u, labels.get(u, ""), words)
        if s > 0:
            ranked.append((s, -len(urlparse(u).path), u))
    ranked.sort(reverse=True)
    return [u for _s, _l, u in ranked[:k]]


def route(ans: dict, pages: list[dict], edition: str = "") -> dict:
    """CODE decides the label. `ans` is the model's JSON; each 'yes' or 'no' survives only if (1) its quote is on the pages, (2) the quote SAYS it, and (3) for a call, the quote is not dated before the edition."""
    ans = dict(ans or {})
    bad = []
    for (k, v), rx in SAYS.items():
        if ans.get(k) != v:
            continue
        q = clean(ans.get(k + "_quote", ""))
        why = ""
        if not q:
            why = "no quote"
        elif not quote_on_pages(q, pages):
            why = "the quote is not on the pages"
        elif not rx.search(q):
            why = "the quote does not say it"
        elif k == "open_call" and v == "yes" and NOT_A_SPEAKERS_CALL.search(q) and not SPEAKER_WORDS.search(q):
            why = "a call for a committee or volunteers, not for speakers"
        elif k == "open_call" and v == "yes" and edition.isdigit():
            years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", q)]
            if years and max(years) < int(edition):
                why = f"dated {max(years)}, before the {edition} edition"
        if why:
            bad.append(f"{k}: {why}")
            ans[k] = "unclear"
    oc, ps, mp = (ans.get("open_call") or "unclear"), (ans.get("paid_slots") or "unclear"), (ans.get("must_pay") or "unclear")
    if mp == "yes":
        r = "MUST_SPONSOR"
    elif oc == "no" and ps != "yes":
        r = "INVITE_ONLY"
    elif oc == "yes" and ps == "yes":
        r = "OPEN_CALL_AND_PAID_SLOTS"
    elif oc == "yes":
        r = "OPEN_CALL"
    elif ps == "yes":
        r = "PAID_SLOTS_NO_CALL_SEEN"
    else:
        r = "UNCLEAR"
    return {"route": r, "open_call": oc, "paid_slots": ps, "must_pay": mp, "dropped": bad,
            "call_quote": clean(ans.get("open_call_quote", "")) if oc in ("yes", "no") else "",
            "paid_quote": clean(ans.get("paid_slots_quote", "")) if ps == "yes" else "",
            "must_quote": clean(ans.get("must_pay_quote", "")) if mp == "yes" else "",
            "summary": clean(ans.get("summary", ""))[:300]}


def build_user(name: str, edition: str, pages: list[dict], per_page: int = 6000) -> str:
    parts = [f"CONFERENCE: {name}   EDITION: {edition or 'not stated'}"]
    for p in pages:
        if (p.get("text") or "").strip():
            parts.append(f"\n=== PAGE kind={p['kind']} url={p['url']} ===\n{re.sub(chr(10) + '{3,}', chr(10) * 2, p['text'])[:per_page]}")
    parts.append("\nReturn ONLY the JSON object.")
    return "\n".join(parts)


# ------------------------------------------------------------------ the table
SCHEMA = """CREATE TABLE IF NOT EXISTS speaking_route (
    event_id TEXT PRIMARY KEY, route TEXT NOT NULL, open_call TEXT, paid_slots TEXT, must_pay TEXT,
    call_quote TEXT, call_url TEXT, paid_quote TEXT, paid_url TEXT, must_quote TEXT, must_url TEXT,
    summary TEXT, edition TEXT, judged_at TEXT, model TEXT, pages_read INTEGER, tokens_in INTEGER, tokens_out INTEGER)"""


def ensure_table(con: sqlite3.Connection) -> None:
    con.execute(SCHEMA)
    con.commit()


def quote_url(quote: str, pages: list[dict]) -> str:
    q = norm(quote)
    if not q:
        return ""
    for p in pages:
        if q in norm(p["text"]):
            return p["url"]
    return ""


def store(con: sqlite3.Connection, event_id: str, res: dict, pages: list[dict], edition: str, toks: tuple[int, int], now: datetime | None = None) -> None:
    ensure_table(con)
    con.execute("INSERT OR REPLACE INTO speaking_route VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (event_id, res["route"], res["open_call"], res["paid_slots"], res["must_pay"], res["call_quote"], quote_url(res["call_quote"], pages),
                 res["paid_quote"], quote_url(res["paid_quote"], pages), res["must_quote"], quote_url(res["must_quote"], pages), res["summary"], edition,
                 (now or datetime.now()).strftime("%Y-%m-%d %H:%M"), MODEL_NAME, sum(1 for p in pages if (p.get("text") or "").strip()), toks[0], toks[1]))
    con.commit()


def load_routes(db) -> dict[str, dict]:
    """{event_id: row} for the page builder; an empty dict when the table does not exist yet. Read-only."""
    try:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            return {r["event_id"]: dict(r) for r in con.execute("select * from speaking_route")}
        finally:
            con.close()
    except sqlite3.Error:
        return {}


def candidates(db, scope_ids: set[str], today: date, stale_days: int = 56, unclear_days: int = 28, limit: int | None = None, only: list[str] | None = None, unreadable_days: int = 14) -> list[dict]:
    """Events to judge: in scope, with a home page; never judged first (live statuses before closed), then the oldest. A decided route is refreshed after stale_days, an UNCLEAR one after unclear_days,
    and an UNCLEAR one where NO page could be read after unreadable_days (nothing was learned: that is a failed read, not an answer)."""
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    has_start = any(c[1] == "start_date" for c in con.execute("pragma table_info(grounding_facts)"))
    rows = [dict(r) for r in con.execute("select event_id, name, url, main_info_url, sponsor_url, sponsor_cost, edition, status, " + ("start_date" if has_start else "'' as start_date") + " from grounding_facts")]
    done = load_routes(db)
    con.close()
    out = []
    for r in rows:
        if r["event_id"] not in scope_ids or not (r["main_info_url"] or r["url"]):
            continue
        if only and r["event_id"] not in only:
            continue
        if not only and str(r.get("start_date") or "")[:10] and str(r["start_date"])[:10] < today.isoformat():
            continue                                                   # the event has already happened: how to speak at it is moot (by its start date, never by the year in its name or URL)
        prev = done.get(r["event_id"])
        if prev and not only:
            age = (today - date.fromisoformat((prev.get("judged_at") or "1970-01-01")[:10])).days
            wait = (unreadable_days if int(prev.get("pages_read") or 0) == 0 else unclear_days) if prev["route"] == "UNCLEAR" else stale_days
            if age < wait:
                continue
        live = str(r["status"] or "").strip().lower() not in ("closed",)
        out.append({**r, "_prev": prev["judged_at"] if prev else "", "_key": (1 if prev else 0, 0 if live else 1, prev["judged_at"] if prev else "")})
    out.sort(key=lambda r: r["_key"])
    return out[:limit] if limit else out


def scope_ids(seed_dir: Path = SEED_DIR) -> set[str]:
    from scripts.check_invariants import CUSTOMER_MARKETS, delivered_ids
    return delivered_ids(seed_dir, CUSTOMER_MARKETS)[0]


# ------------------------------------------------------------------ the network and model parts
class _Q:
    def log(self, *a, **k):
        pass


async def render(url: str, ctx):
    try:
        html, anchors, st, body, _c = await ctx._f._render_with_consent(url, ctx.settings, _Q(), prefer_cdp=True)
        return (body or ""), [((x.get("href") or ""), (x.get("text") or "")[:80]) for x in (anchors or [])][:600]
    except Exception:                                                  # noqa: BLE001
        return "", []


def old_edition_url(u: str, floor: int) -> bool:
    """True when the URL PATH names a year before `floor` (/call-for-papers-2025): an old edition's page. A bare /call-for-papers is evergreen and stays."""
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", urlparse(u).path)]
    return bool(years) and max(years) < floor


async def collect(r: dict, ctx) -> list[dict]:
    home = r["main_info_url"] or r["url"]
    hosts = {host(home), host(r["sponsor_url"] or "")} - {""}
    # HARD ANTI-BOT HOSTS (the fetch layer's own list). They are read through the operator's REAL Chrome (CDP, his own IP and browser fingerprint), the top rung of the fetch ladder, and only when that Chrome is
    # reachable; otherwise they are skipped rather than hammered with plain requests (a flagged residential IP costs more than a missed event). No plain-HTTP sitemap request is made to such a host.
    hard = hasattr(ctx._f, "_force_fallback_domain") and ctx._f._force_fallback_domain(home)
    if hard and not ctx._f.cdp_reachable(getattr(ctx.settings, "cdp_url", None)):
        return []
    urls, labels = [], {}
    if not hard:
        try:
            pages, _how, _cap, _n, _r = await ctx.cs.collect(ctx.sitewalk.origin(home))
            urls += [u for u, _lm in pages]
        except Exception:                                              # noqa: BLE001
            pass
    cache: dict[str, str] = {}
    body, anchors = await render(home, ctx)
    cache[home] = body
    for href, text in anchors:
        u = urljoin(home, href).split("#")[0]
        if host(u) in hosts and u.startswith("http"):
            urls.append(u)
            if text:
                labels[u] = text
    floor = date.today().year          # a link naming a year BEFORE this calendar year is a past edition's page (/2025/ now, /2026/ from 1 Jan 2027). The current year stays: next year's event is often announced on it.
    urls = [u for u in dict.fromkeys(urls) if u in (home, r["sponsor_url"]) or not old_edition_url(u, floor)]   # the home page and the cited sponsor page are always read (the outliers)
    cited = r["sponsor_url"] or ""
    spons = pick(urls, labels, SPONSOR_WORDS, {home, cited}, 3)
    calls = pick(urls, labels, CALL_WORDS, {home, cited, *spons}, 3)
    targets = [("home", home)] + ([("cited-sponsor", cited)] if cited else []) + [("sponsor", u) for u in spons] + [("call", u) for u in calls]
    out = []
    for kind, u in targets:
        text = cache.get(u)
        if text is None:
            text = (await render(u, ctx))[0]
            cache[u] = text
            await asyncio.sleep(2)
        out.append({"kind": kind, "url": u, "text": text[:40000]})
    return out


async def ask(user: str, settings):
    import litellm
    kwargs = dict(model=settings.llm_provider, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], api_key=settings.provider_key(), temperature=0.0, max_tokens=700)
    try:
        resp = await litellm.acompletion(**kwargs, response_format={"type": "json_object"})
    except Exception:                                                  # noqa: BLE001
        resp = await litellm.acompletion(**kwargs)
    raw = resp.choices[0].message.content or ""
    u = getattr(resp, "usage", None)
    m = re.search(r"\{.*\}", raw, re.S)
    return (json.loads(m.group(0)) if m else {}), ((getattr(u, "prompt_tokens", 0) or 0), (getattr(u, "completion_tokens", 0) or 0))


async def run(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    today = date.today()
    ids = scope_ids()
    todo = candidates(a.db, ids, today, a.stale_days, a.unclear_days, a.limit, a.event_id)
    print(f"SPEAKING ROUTE {datetime.now():%Y-%m-%d %H:%M} {'APPLY' if a.apply else 'REPORT ONLY'}: {len(todo)} event(s) to judge (limit {a.limit or 'none'}, {a.max_minutes} minutes)")
    if not todo:
        return 0
    from scripts.shadow_finder import build_ctx
    out = Path(a.out_dir) if a.out_dir else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    ctx = build_ctx((out or Path(a.db).parent) / "speaking_route_reader_log.jsonl", 1.0)
    t0, sem, results, tot_in, tot_out = time.time(), asyncio.Semaphore(a.concurrency), [], 0, 0
    state = {"consecutive_unreadable": 0, "abort": False}
    MAX_UNREADABLE_IN_A_ROW = 8              # eight events in a row with no readable page at all means the browser layer is down (2026-10-19: a dialog crashed the driver), not that eight sites are empty

    async def work(i, r):
        nonlocal tot_in, tot_out
        async with sem:
            if (time.time() - t0) / 60 > a.max_minutes or state["abort"]:
                return
            try:
                pages = await collect(r, ctx)
                edition = str(r.get("edition") or "")
                if not pages:                                                   # a hard anti-bot host and no real Chrome to read it with: collect() skips it. Recorded (retried later), not a browser failure
                    res, toks = route({}, pages, edition), (0, 0)
                    res["summary"] = "hard anti-bot host and no real Chrome reachable: not read"
                elif not any((p["text"] or "").strip() for p in pages):
                    state["consecutive_unreadable"] += 1
                    if state["consecutive_unreadable"] >= MAX_UNREADABLE_IN_A_ROW and not state["abort"]:
                        state["abort"] = True
                        print(f"STOPPED: {MAX_UNREADABLE_IN_A_ROW} events in a row had no readable page; the browser layer looks down. Nothing is recorded for them; run again when it is back.", flush=True)
                    if state["abort"]:
                        print(f"[{i + 1}/{len(todo)}] {r['name'][:46]:46} not read (browser layer down)", flush=True)
                        return
                    res, toks = route({}, pages, edition), (0, 0)
                    res["summary"] = "no readable page"
                else:
                    state["consecutive_unreadable"] = 0
                    ans, toks = await ask(build_user(r["name"], edition, pages), ctx.settings)
                    res = route(ans, pages, edition)
                tot_in += toks[0]
                tot_out += toks[1]
                if a.apply:
                    con = sqlite3.connect(a.db, timeout=60)
                    try:
                        store(con, r["event_id"], res, pages, edition, toks)
                    finally:
                        con.close()
                results.append({"event_id": r["event_id"], "name": r["name"], **{k: res[k] for k in ("route", "call_quote", "paid_quote", "must_quote", "summary", "dropped")}})
                print(f"[{i + 1}/{len(todo)}] {r['name'][:46]:46} {res['route']}", flush=True)
            except Exception as e:                                     # noqa: BLE001  one event never stops the run
                print(f"[{i + 1}/{len(todo)}] {r['name'][:46]:46} error {type(e).__name__}: {str(e)[:100]}", flush=True)

    await asyncio.gather(*(work(i, r) for i, r in enumerate(todo)))
    from collections import Counter
    c = Counter(x["route"] for x in results)
    print(f"done: {len(results)} judged " + ", ".join(f"{k} {v}" for k, v in c.most_common()) + f"; tokens {tot_in}/{tot_out}; about {tot_in * PRICE_IN + tot_out * PRICE_OUT:.3f} USD (estimate)")
    if out:
        (out / "speaking_route_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Speaking route: how a company gets a speaking slot, and whether it must pay.")
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--apply", action="store_true", help="write the table speaking_route. Reports only without it.")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--max-minutes", type=float, default=25)
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--stale-days", type=int, default=56)
    ap.add_argument("--unclear-days", type=int, default=28)
    ap.add_argument("--event-id", nargs="*", help="judge exactly these canonical ids (ignores the age rule)")
    ap.add_argument("--out-dir")
    a = ap.parse_args(argv)
    try:
        return asyncio.run(run(a))
    except (Exception, SystemExit) as e:                               # noqa: BLE001  advisory: it must never fail a weekly job
        print(f"SPEAKING ROUTE: stopped - {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
