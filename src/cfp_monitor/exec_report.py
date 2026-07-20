"""Customer-facing executive rollup: a single self-contained HTML page.

Audience is the PR firm principal, not us. It answers one question -- "what can my clients
act on right now?" -- and deliberately contains NO backend language (no crawler, model,
CDP or quality-gate talk). Every opportunity links straight to the page where you submit.

The five buckets are mutually exclusive and sum to the event total, so the table always
reconciles:

    Open       call is open -- act now
    Upcoming   submission page found AND the site states when the call opens
    Monitoring submission page found, but no open date announced yet
    Closed     the deadline for that edition has passed
    Verify     needs a human: no submission page found, or the data refers to an
               edition that has already gone by

"Page under watch" = Open + Upcoming + Monitoring + Closed, i.e. every event where we have
pinpointed the submission page. That is the honest confidence signal: for those we see the
change the moment the page updates; for Verify nobody is watching anything yet.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from typing import Optional

from .filtering import days_until
from .storage import Store

BUCKETS = ["Open", "Upcoming", "Monitoring", "Closed", "Verify"]
_BUCKET_NOTE = {
    "Open": "Call is open - act now",
    "Upcoming": "Submission page found and the site states when the call opens",
    "Monitoring": "Submission page found; no open date announced yet",
    "Closed": "Deadline passed for that edition",
    "Verify": "Needs a human: no submission page found, or the edition has gone by",
}


def _stale(rec: dict, year: int) -> bool:
    """The record's verdict refers to an edition that has already gone by."""
    if rec.get("event_is_past") == 1:
        return True
    ed = rec.get("edition")
    try:
        return bool(ed) and int(ed) < year
    except (TypeError, ValueError):
        return False


def bucket_of(rec: dict, year: int) -> str:
    status = (rec.get("cfp_status") or "").lower()
    has_page = bool((rec.get("submission_url") or "").strip())
    if status == "closed":
        return "Closed"
    if _stale(rec, year):
        return "Verify"          # a live-sounding verdict on a dead edition is not trustworthy
    if status == "open":
        return "Open"
    if status == "upcoming":
        return "Upcoming"
    return "Monitoring" if has_page else "Verify"


def verify_reason(rec: dict, year: int) -> str:
    if _stale(rec, year):
        return "Information refers to an edition that has passed - needs re-checking"
    return "No submission page found yet - needs a manual look"


def _deadline_note(rec: dict, today: date) -> str:
    """Only ever claim urgency when the deadline parses to a real date."""
    raw = (rec.get("cfp_close_date") or "").strip()
    if not raw:
        return "No deadline published"
    n = days_until(raw, today)
    if n is None:
        return html.escape(raw)
    if n < 0:
        return f"{html.escape(raw)} (passed)"
    if n <= 30:
        return f"{html.escape(raw)} - closes in {n} days"
    return html.escape(raw)


def build_report(store: Store, title: str = "Speaking &amp; Awards Opportunities",
                 new_since_days: int = 7, today: Optional[date] = None,
                 detail: bool = False, sheets_note: str = "", sheets_url: str = "") -> str:
    """`detail=False` renders the executive summary only (KPIs + the reconciling rollup).
    `detail=True` adds the "new since last update" list and the expandable per-market tables
    with Submit links -- kept for when the process has matured."""
    today = today or date.today()
    year = today.year
    cutoff = (datetime.combine(today, datetime.min.time()) - timedelta(days=new_since_days)).isoformat()

    records = store.all_records()
    markets_by_key: dict[str, list[str]] = {}
    for row in store.db.execute(
            "SELECT conference_key, market FROM conference_markets ORDER BY market"):
        markets_by_key.setdefault(row[0], []).append(row[1])

    for r in records:
        r["_bucket"] = bucket_of(r, year)
        r["_markets"] = markets_by_key.get(r["key"], [])
        r["_new"] = bool(r.get("first_seen") and str(r["first_seen"]) >= cutoff)

    markets = sorted({m for r in records for m in r["_markets"]})
    counts = {m: {b: 0 for b in BUCKETS} for m in markets}
    for r in records:
        for m in r["_markets"]:
            counts[m][r["_bucket"]] += 1
    totals = {b: sum(1 for r in records if r["_bucket"] == b) for b in BUCKETS}
    n_events = len(records)
    watched = n_events - totals["Verify"]
    pipeline = totals["Upcoming"] + totals["Monitoring"]
    nice_date = f"{today.strftime('%d %B %Y').lstrip('0')}"
    new_events = [r for r in records if r["_new"]]

    def rank(r: dict) -> tuple:
        order = {b: i for i, b in enumerate(BUCKETS)}
        n = days_until((r.get("cfp_close_date") or ""), today)
        return (order[r["_bucket"]], n if n is not None else 9999, (r.get("name") or "").lower())

    # ---- per-market detail ----
    sections = []
    for m in markets:
        rows = sorted([r for r in records if m in r["_markets"]], key=rank)
        c = counts[m]
        chips = " ".join(
            f'<span class="chip b-{b.lower()}">{c[b]} {b}</span>' for b in BUCKETS if c[b])
        items = []
        for r in rows:
            b = r["_bucket"]
            name = html.escape(r.get("name") or "(name not captured)")
            site = html.escape(r.get("url") or "")
            sub = (r.get("submission_url") or "").strip()
            ed = html.escape(r.get("edition") or "")
            loc = html.escape(r.get("location") or "")
            mine = html.escape(r.get("submission_status") or "")
            action = (f'<a class="go" href="{html.escape(sub)}" target="_blank" rel="noopener">Submit &rarr;</a>'
                      if sub else "")
            note = (verify_reason(r, year) if b == "Verify"
                    else _deadline_note(r, today))
            items.append(
                f'<tr class="r b-{b.lower()}" data-bucket="{b}" data-edition="{ed}" data-mine="{mine}">'
                f'<td class="nm"><a href="{site}" target="_blank" rel="noopener">{name}</a>'
                f'{"<span class=new>NEW</span>" if r["_new"] else ""}'
                f'{f"<div class=sub>{loc}</div>" if loc else ""}</td>'
                f'<td><span class="tag b-{b.lower()}">{b}</span></td>'
                f'<td>{ed or "&mdash;"}</td>'
                f'<td class="dl">{note}</td>'
                f'<td>{mine or "&mdash;"}</td>'
                f'<td class="act">{action}</td></tr>')
        sections.append(
            f'<details class="mkt"><summary><span class="mname">{html.escape(m)}</span>'
            f'<span class="mcount">{len(rows)} events</span>{chips}</summary>'
            f'<div class="tw"><table class="ev"><thead><tr>'
            f'<th>Conference</th><th>Status</th><th>Edition</th>'
            f'<th>Deadline / next step</th><th>Your status</th><th></th>'
            f'</tr></thead><tbody>{"".join(items)}</tbody></table></div></details>')

    head = "".join(f'<th class="n">{b}</th>' for b in BUCKETS)
    body = "".join(
        f'<tr><td class="mk">{html.escape(m)}</td><td class="tot">{sum(counts[m].values())}</td>'
        + "".join(f'<td class="n b-{b.lower()}">{counts[m][b] or "&middot;"}</td>' for b in BUCKETS)
        + "</tr>" for m in markets)
    foot = ("".join(f'<td class="n">{totals[b]}</td>' for b in BUCKETS))
    editions = sorted({r.get("edition") for r in records if r.get("edition")}, reverse=True)
    ed_opts = "".join(f'<option value="{html.escape(e)}">{html.escape(e)}</option>' for e in editions)

    new_block = ""
    if new_events:
        li = "".join(
            f'<li><a href="{html.escape(r.get("url") or "")}" target="_blank" rel="noopener">'
            f'{html.escape(r.get("name") or "(name not captured)")}</a> '
            f'<span class="tag b-{r["_bucket"].lower()}">{r["_bucket"]}</span> '
            f'<span class="sub">{html.escape(", ".join(r["_markets"]))}</span></li>'
            for r in sorted(new_events, key=rank)[:40])
        new_block = (f'<section><h2>New since last update</h2>'
                     f'<p class="lede">{len(new_events)} newly identified in the last '
                     f'{new_since_days} days.</p><ul class="new-list">{li}</ul></section>')

    legend = " ".join(f'<span class="lg"><b class="tag b-{b.lower()}">{b}</b> {_BUCKET_NOTE[b]}</span>'
                      for b in BUCKETS)

    if detail:
        lower = (new_block
                 + '<section><h2>Browse by market</h2><div class="controls">'
                 + '<select id="fb"><option value="">All statuses</option>'
                 + "".join(f"<option>{b}</option>" for b in BUCKETS)
                 + f'</select><select id="fe"><option value="">All editions</option>{ed_opts}</select>'
                 + '<button id="fo">Open only</button><button id="fr">Reset</button></div>'
                 + "".join(sections) + '</section>')
        footer = ('Each conference links to its own site; <b>Submit &rarr;</b> goes straight to the '
                  'submission page. &ldquo;Your status&rdquo; is yours to maintain &mdash; we never change it.')
    else:
        lower = ""
        footer = ('Full detail for every event &mdash; deadlines, submission links and notes &mdash; '
                  'lives in the per-market sheets.')
    if sheets_note or sheets_url:
        label = html.escape(sheets_note) if sheets_note else "Open the market sheets"
        where = (f'<a class="go" href="{html.escape(sheets_url)}">{label}</a>'
                 if sheets_url else f'<span class="where">{label}</span>')
        lower = (f'<section class="sheets"><h2>Individual market sheets</h2>'
                 f'<p class="lede">One spreadsheet per market, with every event, deadline and '
                 f'submission link.</p>{where}</section>') + lower

    return f"""<title>{title}</title>
<style>
:root{{--bg:#f6f7f8;--card:#fff;--ink:#16181d;--mut:#5d6570;--line:#e3e6e8;
--open:#12805f;--upcoming:#1a6fb5;--monitoring:#7a5cb8;--closed:#8a8f97;--verify:#b0761a;
--accent:#12805f;--accent-soft:#12805f14;--accent-line:#12805f45;--shadow:0 1px 2px rgba(16,20,24,.05),0 8px 28px rgba(16,20,24,.06)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#14171c;--card:#1b1f26;--ink:#e9ecef;--mut:#98a1ad;
--line:#2b313a;--open:#43b892;--upcoming:#5aa6e0;--monitoring:#a68ae0;--closed:#8b929b;--verify:#d9a147;
--accent:#43b892;--accent-soft:#43b89224;--accent-line:#43b89255;--shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.32)}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,
'Segoe UI',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1120px;margin:0 auto;padding:clamp(22px,4vw,52px) clamp(16px,3vw,32px) 72px}}
h1{{font-size:clamp(23px,3.6vw,33px);margin:0 0 6px;letter-spacing:-.01em}}
h2{{font-size:19px;margin:0 0 4px;letter-spacing:-.01em}}
.lede{{color:var(--mut);margin:0 0 18px}}
.meta{{color:var(--mut);font-size:13px;margin-bottom:26px}}
.hero{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
flex-wrap:wrap;padding-bottom:18px;border-bottom:1px solid var(--line);margin-bottom:24px}}
.hsub{{color:var(--mut);margin:6px 0 0;font-size:14px}}
.tools{{display:flex;gap:8px}}
.kpi.lead{{background:var(--accent-soft);border-color:var(--accent-line)}}
.kpi.lead .v{{font-size:40px;color:var(--accent)}} .kpi.lead .l{{color:var(--mut);font-size:13px}}
.of{{font-size:16px;color:var(--mut)}}
@media print{{
  .tools{{display:none}} body{{background:#fff}}
  .kpi,.roll,details.mkt{{box-shadow:none}}
  .kpi.lead{{background:#fff;border:1.5px solid var(--accent)}}
  section{{break-inside:avoid}}
}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:26px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow)}}
.kpi .v{{font-size:29px;font-weight:650;letter-spacing:-.02em}}
.kpi .l{{color:var(--mut);font-size:12.5px;margin-top:2px}}
section{{margin-bottom:30px}}
.tw{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;background:var(--card);font-size:14px}}
.roll{{border:1px solid var(--line);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}}
th{{text-align:left;font-size:11.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);
font-weight:600;padding:11px 12px;border-bottom:1px solid var(--line);white-space:nowrap}}
td{{padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
th.n,td.n,td.tot{{text-align:center;font-variant-numeric:tabular-nums}}
.mk{{text-align:left;font-weight:550}} .tfoot td{{font-weight:650;background:rgba(125,125,125,.06)}}
.b-open{{color:var(--open)}}.b-upcoming{{color:var(--upcoming)}}.b-monitoring{{color:var(--monitoring)}}
.b-closed{{color:var(--closed)}}.b-verify{{color:var(--verify)}}
.tag{{display:inline-block;font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:99px;
border:1px solid currentColor;white-space:nowrap}}
.chip{{font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:99px;border:1px solid currentColor;margin-left:6px}}
details.mkt{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;
box-shadow:var(--shadow);overflow:hidden}}
summary{{cursor:pointer;padding:14px 16px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:'\\25B8';color:var(--mut);transition:transform .15s}}
details[open] summary::before{{transform:rotate(90deg)}}
.mname{{font-weight:600}} .mcount{{color:var(--mut);font-size:13px;margin-right:auto;margin-left:4px}}
.nm a{{color:var(--ink);text-decoration:none;font-weight:550}} .nm a:hover{{text-decoration:underline}}
.sub{{color:var(--mut);font-size:12.5px}}
.new{{background:var(--accent);color:var(--card);font-size:10px;font-weight:700;padding:1px 6px;
border-radius:99px;margin-left:7px;letter-spacing:.04em}}
.go{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;font-size:12.5px;
font-weight:600;padding:5px 11px;border-radius:7px;white-space:nowrap}}
.dl{{color:var(--mut)}} .act{{text-align:right}}
.controls{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}}
select,button{{font:inherit;font-size:13px;padding:7px 10px;border-radius:8px;border:1px solid var(--line);
background:var(--card);color:var(--ink)}}
button{{cursor:pointer}}
.where{{display:inline-block;background:var(--accent-soft);border:1px solid var(--accent-line);
color:var(--ink);padding:9px 13px;border-radius:8px;font-size:13.5px}}
.legend{{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--mut);font-size:12.5px;margin-top:8px}}
.new-list{{margin:0;padding-left:18px}} .new-list li{{margin:4px 0}}
footer{{color:var(--mut);font-size:12.5px;border-top:1px solid var(--line);padding-top:16px;margin-top:34px}}
a{{color:var(--accent)}}
</style>
<div class="wrap">
<header class="hero">
  <div>
    <h1>{title}</h1>
    <p class="hsub">{len(markets)} markets &middot; {n_events} events tracked &middot; updated {nice_date}</p>
  </div>
  <div class="tools"><button id="dl">Download</button><button id="pr">Print / PDF</button></div>
</header>

<div class="kpis">
  <div class="kpi lead">
    <div class="v">{totals['Open']}</div>
    <div class="l">Open now &mdash; ready to submit</div>
  </div>
  <div class="kpi"><div class="v b-upcoming">{pipeline}</div>
    <div class="l">In the pipeline &mdash; watching for the call</div></div>
  <div class="kpi"><div class="v">{watched}<span class="of">/{n_events}</span></div>
    <div class="l">Submission page under watch</div></div>
  <div class="kpi"><div class="v">{len(markets)}</div><div class="l">Markets covered</div></div>
</div>

<section>
  <h2>Opportunities by market</h2>
  <p class="lede">Every row adds up to its event total.</p>
  <div class="tw"><table class="roll"><thead><tr><th>Market</th><th class="n">Events</th>{head}</tr></thead>
  <tbody>{body}</tbody>
  <tfoot class="tfoot"><tr><td class="mk">All markets (unique)</td><td class="tot">{n_events}</td>{foot}</tr></tfoot>
  </table></div>
  <div class="legend">{legend}</div>
</section>

{lower}
<footer>{footer}</footer>
</div>
<script>
(function(){{
  var d=document.getElementById('dl'),pr=document.getElementById('pr');
  if(pr) pr.onclick=function(){{window.print();}};
  if(d) d.onclick=function(){{
    // Self-contained snapshot: styles are inline, so the saved file opens anywhere offline.
    var blob=new Blob(['<!doctype html>
'+document.documentElement.outerHTML],
                      {{type:'text/html;charset=utf-8'}});
    var a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='opportunities-{today.isoformat()}.html'; document.body.appendChild(a); a.click();
    document.body.removeChild(a); setTimeout(function(){{URL.revokeObjectURL(a.href);}},1000);
  }};
  var fb=document.getElementById('fb'),fe=document.getElementById('fe');
  if(!fb||!fe) return;   // summary mode has no filter controls
  function apply(){{
    var b=fb.value,e=fe.value;
    document.querySelectorAll('tr.r').forEach(function(r){{
      var ok=(!b||r.dataset.bucket===b)&&(!e||r.dataset.edition===e);
      r.style.display=ok?'':'none';
    }});
    document.querySelectorAll('details.mkt').forEach(function(d){{
      var any=d.querySelectorAll('tr.r:not([style*="none"])').length;
      d.style.display=any?'':'none'; if((b||e)&&any) d.open=true;
    }});
  }}
  fb.onchange=fe.onchange=apply;
  document.getElementById('fo').onclick=function(){{fb.value='Open';apply();}};
  document.getElementById('fr').onclick=function(){{fb.value='';fe.value='';apply();
    document.querySelectorAll('details.mkt').forEach(function(d){{d.open=false;d.style.display='';}});}};
}})();
</script>
"""
