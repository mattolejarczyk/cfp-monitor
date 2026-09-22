"""The evidence matrix: for every conference and field, the value, HOW DEEP we went for evidence,
and the source + verbatim quote behind it. One page, two levels: a flat filterable heatmap on top
(scan and filter), each row expands to its full per-field evidence card (drill to the proof).

Provenance is a numbered ladder - how deep a field had to climb for evidence. AI search (L1
upstream, L6 our grounded) costs money; our own code (L2-L5) is free. `unv` = a value we hold but
have not proven; a blank = no value at all. Reads grounding_facts (current value + deadline
provenance), the evidence table (per-field claims + verbatim quotes, incl. verify_dates), and
client_conferences (the customer overlay - read, never written).

    python scripts/evidence_matrix.py --db <live.db> [--out PATH] [--limit N]
    python scripts/evidence_matrix.py --db <live.db> --refresh   # rebuild evidence first
"""
import argparse
import html
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

LAYERS = {1: ("L1", "AI search (upstream)", True), 2: ("L2", "Code verify", False),
          3: ("L3", "Code: deadline passed", False), 4: ("L4", "Code: plain fetch", False),
          5: ("L5", "Code: browser", False), 6: ("L6", "AI search $ (ours)", True)}
SELFHEAL_LAYER = {"deadline-passed": 3, "fetch-plain+regex": 4,
                  "browser-ladder+regex": 5, "grounded-search+verify": 6}
# display field -> (grounding_facts value column, evidence field name)
FIELDS = [("Deadline", "deadline", "_deadline"), ("Venue", "_loc", "venue"),
          ("Dates", "start_date", "conference_dates"), ("Sub URL", "submission_url", "submission_url"),
          ("Status", "status", "status"), ("Lifecycle", "lifecycle_quote", "lifecycle")]


def hostof(u):
    try:
        return urlparse(u or "").netloc.replace("www.", "")
    except Exception:
        return ""


def best_evidence(con, eid, efield):
    return con.execute(
        "SELECT origin, verdict, source_url, COALESCE(found_quote, quote, '') q FROM evidence "
        "WHERE event_id=? AND field=? ORDER BY (verdict='verified') DESC, (origin='grounding') DESC "
        "LIMIT 1", (eid, efield)).fetchone()


def field_state(con, eid, gf, gcol, efield):
    """Return (state, source_url, quote). state in 1..6 | 'unv' | None."""
    if efield == "_deadline":
        vs, vd = gf["verify_state"], gf["verify_detail"] or ""
        url, q = gf["deadline_evidence_url"], gf["deadline_quote"]
        if vd.startswith("self-heal:"):
            return SELFHEAL_LAYER.get(vd.split(":", 1)[1], 4), url, q
        if vs == "verified":
            return 2, url, q
        return ("unv", url, q) if (gf["deadline"] or "").strip() else (None, "", "")
    ev = best_evidence(con, eid, efield)
    if ev:
        if ev["verdict"] == "verified":
            return (2 if ev["origin"] == "crawl" else 1), ev["source_url"], ev["q"]
        if ev["origin"] == "grounding":
            return 1, ev["source_url"], ev["q"]
    return ("unv", "", "") if (gf.get(gcol) or "").strip() else (None, "", "")


def cell(state):
    if state is None:
        return '<td class="c cx">&mdash;</td>'
    if state == "unv":
        return '<td class="c cu" title="value present, not proven">unv</td>'
    tag = LAYERS[state][0]
    return f'<td class="c c{state}">{tag}{"$" if state == 6 else ""}</td>'


def build(con, limit):
    con.row_factory = sqlite3.Row
    q = ("SELECT gf.event_id FROM grounding_facts gf JOIN evidence e ON e.event_id=gf.event_id "
         "LEFT JOIN client_conferences cc ON cc.event_id=gf.event_id GROUP BY gf.event_id "
         "ORDER BY (COUNT(DISTINCT cc.client_key)>0) DESC, COUNT(e.id) DESC")
    eids = [r[0] for r in con.execute(q).fetchall()]
    if limit:
        eids = eids[:limit]

    flat, cards, markets = [], [], set()
    for i, eid in enumerate(eids):
        gf = dict(con.execute("SELECT * FROM grounding_facts WHERE event_id=?", (eid,)).fetchone())
        gf["_loc"] = ", ".join([x for x in (gf.get("city"), gf.get("state_province"), gf.get("country")) if x])
        clients = sorted({r[0] for r in con.execute("SELECT client_key FROM client_conferences WHERE event_id=?", (eid,))})
        mkt = (gf.get("categories") or "-").split(",")[0][:20] or "-"
        markets.add(mkt)

        states, hit, paid, crows = [], [], False, []
        for label, gcol, efield in FIELDS:
            st, url, quote = field_state(con, eid, gf, gcol, efield)
            states.append(st)
            if isinstance(st, int):
                hit.append(st)
                paid = paid or st == 6
            val = gf.get(gcol) or ""
            btag = LAYERS[st][1] if isinstance(st, int) else ("value, unproven" if st == "unv" else "no value")
            src = f'<a href="{html.escape(url)}" target="_blank">{html.escape(hostof(url))}</a>' if url else '<span class="muted">-</span>'
            crows.append(f'<tr><td class="f">{html.escape(label)}</td>'
                         f'<td>{html.escape(str(val)[:80]) or "<span class=muted>(blank)</span>"}</td>'
                         f'<td><span class="pv {("c"+str(st)) if isinstance(st,int) else ("cu" if st=="unv" else "cx")}">{html.escape(btag)}</span></td>'
                         f'<td class="src">{src}</td>'
                         f'<td class="q">{("&quot;"+html.escape(quote[:160])+"&quot;") if quote else "<span class=muted>no quote</span>"}</td></tr>')
        maxd = max(hit, default=None)
        cli = " ".join(f'<span class="cli">{html.escape(x)}</span>' for x in clients)
        flat.append(
            f'<tr class="row" data-i="{i}" data-mkt="{html.escape(mkt)}" data-paid="{1 if paid else 0}" '
            f'data-maxd="{maxd or 0}" onclick="tog({i})">'
            f'<td class="nm">{html.escape(gf["name"][:46])}<div class="sub">{cli}</div></td>'
            f'<td class="mkt">{html.escape(mkt)}</td>' + "".join(cell(s) for s in states)
            + f'<td class="c maxd">{("L"+str(maxd)) if maxd else "-"}</td>'
            + f'<td class="c">{"<span class=paidy>$</span>" if paid else "<span class=free>free</span>"}</td></tr>')
        flat.append(
            f'<tr id="d{i}" class="detail" style="display:none"><td colspan="{len(FIELDS)+4}">'
            f'<div class="card"><table class="ct"><thead><tr><th>Field</th><th>Value</th>'
            f'<th>Where it came from</th><th>Source</th><th>Verbatim evidence</th></tr></thead>'
            f'<tbody>{"".join(crows)}</tbody></table></div></td></tr>')
    return flat, sorted(markets), len(eids)


STYLE = """
:root{--paper:#f5f6f8;--card:#fff;--sunk:#eceef2;--ink:#161a20;--ink2:#535c67;--ink3:#8a929c;--rule:#dde0e6;--link:#3a4f8c;
--l1:#e3edf5;--l1t:#2a5b87;--l2:#e4efe8;--l2t:#2c6a4d;--l3:#eaf6ef;--l3t:#2c6a4d;--l4:#fbf3df;--l4t:#8f6317;
--l5:#f7ead9;--l5t:#8f6317;--l6:#f7e0e0;--l6t:#9a3434;--lx:#eceef2;--lxt:#8a929c;--lu:#f0ecda;--lut:#8f7d3c;}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#101318;--card:#181c22;--sunk:#0b0e12;
--ink:#e6e8ec;--ink2:#a6aeb9;--ink3:#767e89;--rule:#272c34;--link:#8ea3e0;
--l1:#142230;--l1t:#7fb0d9;--l2:#16251d;--l2t:#7fc39c;--l3:#16251d;--l3t:#7fc39c;--l4:#2a2114;--l4t:#d9ab60;
--l5:#2a2114;--l5t:#d9ab60;--l6:#331717;--l6t:#e08585;--lx:#1e2229;--lxt:#767e89;--lu:#26240f;--lut:#c9b96a;}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Source Sans 3",Segoe UI,sans-serif;font-size:15px;padding:2rem 1rem 4rem}
.wrap{max-width:1120px;margin:0 auto}h1{font-size:1.6rem;margin:0 0 .3rem}.lead{color:var(--ink2);max-width:78ch;margin:0 0 .8rem}
.legend{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin:.5rem 0;font-size:.8rem;color:var(--ink2)}
.lg,.pv{font:600 .62rem/1 "JetBrains Mono",monospace;padding:.22rem .42rem;border-radius:3px}
.c1,.lg.c1,.pv.c1{background:var(--l1);color:var(--l1t)}.c2,.lg.c2,.pv.c2{background:var(--l2);color:var(--l2t)}
.c3,.pv.c3{background:var(--l3);color:var(--l3t)}.c4,.pv.c4{background:var(--l4);color:var(--l4t)}
.c5,.lg.c5,.pv.c5{background:var(--l5);color:var(--l5t)}.c6,.lg.c6,.pv.c6{background:var(--l6);color:var(--l6t)}
.cx,.lg.cx,.pv.cx{background:var(--lx);color:var(--lxt)}.cu,.lg.cu,.pv.cu{background:var(--lu);color:var(--lut)}
.controls{display:flex;gap:.6rem;flex-wrap:wrap;margin:.7rem 0;font-size:.82rem}
select{font:inherit;padding:.2rem .4rem;border:1px solid var(--rule);border-radius:4px;background:var(--card);color:var(--ink)}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.82rem}
th,td{padding:.45rem .5rem;border-bottom:1px solid var(--rule);text-align:center}
th{font:600 .6rem/1.2 "JetBrains Mono",monospace;letter-spacing:.04em;text-transform:uppercase;color:var(--ink3);white-space:nowrap}
td.nm{text-align:left;font-weight:600;white-space:nowrap;cursor:pointer}td.mkt{text-align:left;color:var(--ink2);white-space:nowrap}
.row{cursor:pointer}.row:hover td{background:var(--sunk)}.sub{font-weight:400;margin-top:.15rem}
.cli{font:.6rem "JetBrains Mono",monospace;background:var(--sunk);color:var(--ink2);padding:.1rem .3rem;border-radius:3px;margin-right:.2rem}
td.c{font:600 .68rem/1 "JetBrains Mono",monospace}.paidy{color:var(--l6t);font-weight:700}.free{color:var(--l2t)}.maxd{font-weight:700}
.detail td{background:var(--sunk);padding:0}.card{padding:.6rem 1rem}
.ct th,.ct td{text-align:left;border-bottom:1px solid var(--rule)}.ct td.f{font-weight:600;white-space:nowrap}
.ct td.q{font-style:italic;color:var(--ink2);max-width:340px}.ct td.src a{color:var(--link);font:.78rem "JetBrains Mono",monospace;text-decoration:none}
.muted{color:var(--ink3)}footer{font:.7rem "JetBrains Mono",monospace;color:var(--ink3);border-top:1px solid var(--rule);padding-top:1rem;margin-top:1.6rem}
"""
JS = """
function tog(i){var d=document.getElementById('d'+i);d.style.display=d.style.display=='none'?'':'none';}
function applyFilters(){var mk=document.getElementById('fmkt').value,pd=document.getElementById('fpaid').value,dp=document.getElementById('fdepth').value;
document.querySelectorAll('tr.row').forEach(function(tr){var ok=(mk==''||tr.dataset.mkt==mk)&&(pd==''||tr.dataset.paid==pd)&&(dp==''||(+tr.dataset.maxd)>=(+dp));
tr.style.display=ok?'':'none';var d=document.getElementById('d'+tr.dataset.i);if(d&&!ok)d.style.display='none';});}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the evidence matrix (flat heatmap + drill-down).")
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", default=str(ROOT / "runs_out" / f"evidence_matrix_{date.today():%Y%m%d}.html"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true", help="run build_evidence.py first so it is current")
    a = ap.parse_args()

    if a.refresh:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_evidence.py"), "--db", a.db], check=False)

    con = sqlite3.connect(a.db)
    flat, markets, n = build(con, a.limit)
    mkt_opts = "".join(f'<option value="{html.escape(m)}">{html.escape(m)}</option>' for m in markets)
    heads = "".join(f"<th>{l}</th>" for l, _g, _e in FIELDS)
    doc = f"""<title>CFP Evidence Matrix</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Source+Sans+3:wght@400;600&display=swap">
<style>{STYLE}</style>
<div class="wrap">
<h1>CFP Evidence Matrix &middot; {date.today():%Y-%m-%d}</h1>
<p class="lead">Every conference and field: the value, <b>how deep we went for evidence</b>, and the
proof behind it. <b>AI search</b> (L1 upstream, L6 ours) costs money; <b>Code</b> (L2-L5) is our own
deterministic checks - free. <b>unv</b> = value held but unproven; <b>&mdash;</b> = no value.
<b>Click any row</b> to see its per-field source and verbatim quote.</p>
<div class="legend"><b>AI $:</b> <span class="lg c1">L1 upstream</span><span class="lg c6">L6 ours $</span>
 &nbsp;<b>Code:</b> <span class="lg c2">L2 verify</span><span class="lg c3">L3 passed</span>
 <span class="lg c4">L4 plain</span><span class="lg c5">L5 browser</span>
 &nbsp;<span class="lg cu">unv</span><span class="lg cx">&mdash;</span></div>
<div class="controls">
 <label>Market <select id="fmkt" onchange="applyFilters()"><option value="">all</option>{mkt_opts}</select></label>
 <label>Cost <select id="fpaid" onchange="applyFilters()"><option value="">all</option><option value="1">paid ($)</option><option value="0">free</option></select></label>
 <label>Min depth <select id="fdepth" onchange="applyFilters()"><option value="">any</option><option value="3">L3+</option><option value="4">L4+</option><option value="5">L5+</option><option value="6">L6</option></select></label>
</div>
<div class="scroll"><table><thead><tr><th>Conference</th><th>Market</th>{heads}<th>Max depth</th><th>Cost</th></tr></thead>
<tbody>{"".join(flat)}</tbody></table></div>
<footer>{n} conferences &middot; grounding_facts + evidence table (incl. verify_dates) + client_conferences.
Generated by evidence_matrix.py.</footer></div><script>{JS}</script>"""
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}  ({n} conferences)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
