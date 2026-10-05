"""The control list: the action list behind the failure-point register, as data, a page and a few safe commands (2026-10-05).

    python scripts/control_list.py render                       # docs/control/ACTION-LIST.html from docs/control/action_list.json
    python scripts/control_list.py validate
    python scripts/control_list.py summary
    python scripts/control_list.py set ACT-10 --state review --evidence "branch builder/wave1 abc123; tests/test_x.py"
    python scripts/control_list.py verify ACT-10 --evidence "reviewed; full suite 1,5xx passed; sandbox rehearsal clean"

ROLES. The builder agent may use `set` (todo, building, review, waiting, needs-you, conditional) and must attach evidence when it hands an action over for review. Only the reviewer uses `verify`.
`verify` marks the action verified AND applies its `on_verify` rules to docs/operations/failure_points.json (a failure point's status and its 'remains' text), then regenerates
docs/operations/FAILURE-POINTS.md and the page, so the two documents cannot disagree. A verified action must carry evidence.
WHY DATA + GENERATOR: the operator wants a document that is easy to read and easy to update. The data is one JSON file; the page is a self-contained HTML file with filters, per-wave progress and a 'Needs you' strip.
Writes only the control list files and, on verify, the register files. Reads nothing else."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "docs" / "control" / "action_list.json"
OUT = ROOT / "docs" / "control" / "ACTION-LIST.html"
FP_DATA = ROOT / "docs" / "operations" / "failure_points.json"
STATES = ("todo", "building", "review", "verified", "waiting", "needs-you", "conditional")
BUILDER_STATES = tuple(s for s in STATES if s != "verified")
FP_STATUSES = ("OVERCOME", "MITIGATED", "WATCH", "PENDING")


def load(path: Path = DATA) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(d: dict, path: Path = DATA) -> None:
    Path(path).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def validate(d: dict, fp: dict | None = None) -> list[str]:
    errs, ids = [], set()
    waves = {w["id"] for w in d["waves"]}
    fp_ids = {i["id"] for i in fp["items"]} if fp else None
    steps = set(fp["steps"]) if fp else set("ABCDEF")
    for a in d["actions"]:
        i = a.get("id", "?")
        if i in ids:
            errs.append(f"duplicate id {i}")
        ids.add(i)
        for k in ("wave", "step", "owner", "state", "title", "detail", "cost", "acceptance"):
            if not a.get(k):
                errs.append(f"{i}: missing {k}")
        if a.get("wave") not in waves:
            errs.append(f"{i}: unknown wave {a.get('wave')}")
        if a.get("step") not in steps:
            errs.append(f"{i}: unknown step {a.get('step')}")
        if a.get("owner") not in d["owners"]:
            errs.append(f"{i}: unknown owner {a.get('owner')}")
        if a.get("state") not in STATES:
            errs.append(f"{i}: unknown state {a.get('state')}")
        if a.get("state") == "verified" and not a.get("evidence"):
            errs.append(f"{i}: verified without evidence")
        if a.get("state") == "needs-you" and not a.get("needs_you"):
            errs.append(f"{i}: needs-you without a stated ask")
        for c in a.get("closes", []):
            if fp_ids is not None and c not in fp_ids:
                errs.append(f"{i}: closes unknown failure point {c}")
        for c, rule in (a.get("on_verify") or {}).items():
            if c not in a.get("closes", []):
                errs.append(f"{i}: on_verify names {c} which it does not close")
            if rule.get("status") and rule["status"] not in FP_STATUSES:
                errs.append(f"{i}: on_verify status {rule['status']} is not a register status")
    for a in d["actions"]:
        for dep in a.get("depends", []):
            if dep not in ids:
                errs.append(f"{a['id']}: depends on unknown {dep}")
    return errs


def counts(d: dict) -> dict:
    return {s: sum(1 for a in d["actions"] if a["state"] == s) for s in STATES}


def page_data(d: dict, fp: dict) -> dict:
    return {"as_of": d["as_of"], "title": d["title"], "intro": d["intro"], "waves": d["waves"], "owners": d["owners"], "actions": d["actions"],
            "steps": fp["steps"], "fp": {i["id"]: i["status"] for i in fp["items"]}}


def apply_verify(d: dict, fp: dict, action_id: str, evidence: str, today: str) -> list[str]:
    """Mark the action verified and apply its on_verify rules to the failure-point data. Returns the register changes made."""
    a = next((x for x in d["actions"] if x["id"] == action_id), None)
    if a is None:
        raise SystemExit(f"no action {action_id}")
    if not evidence.strip():
        raise SystemExit("verify needs --evidence: a verified action must say what was checked")
    a["state"] = "verified"
    a["needs_you"] = ""
    a.setdefault("evidence", []).append(evidence.strip())
    a["updated"] = today
    changes = []
    by_id = {i["id"]: i for i in fp["items"]}
    for fid, rule in (a.get("on_verify") or {}).items():
        item = by_id[fid]
        if rule.get("status") and rule["status"] != item["status"]:
            changes.append(f"{fid}: {item['status']} -> {rule['status']}")
            item["status"] = rule["status"]
            if rule["status"] == "OVERCOME":
                item["since"] = today
        if rule.get("remains"):
            item["remains"] = rule["remains"]
            changes.append(f"{fid}: remains updated")
        item["controls"] = (item["controls"] + f" [{action_id}, verified {today}]").strip()
    fp["as_of"] = today
    return changes


# ------------------------------------------------------------------------------------------ the page
TEMPLATE = r'''<title>CFP Control List</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
/* Layout: a working list. Summary and the "Needs you" strip first, then waves; each action is one expandable row. Colour carries state, never decoration. */
:root{--bg:#f4f6f5;--surface:#ffffff;--ink:#1c2523;--muted:#5a6663;--line:#dce2df;--accent:#0f6b66;--accent-bg:#e2f1ef;
--s-todo:#6b7673;--s-todo-bg:#e8ecea;--s-building:#2457a6;--s-building-bg:#e3ecf9;--s-review:#7a4fb0;--s-review-bg:#eee6f8;--s-verified:#1f7a46;--s-verified-bg:#e0f3e8;
--s-waiting:#8a6100;--s-waiting-bg:#f8efd3;--s-needs:#b3261e;--s-needs-bg:#fbe4e1;--s-cond:#5b6f8a;--s-cond-bg:#e6ebf2;
--font:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,"Cascadia Mono",Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121816;--surface:#1a2220;--ink:#e6ecea;--muted:#9aa7a3;--line:#2c3835;--accent:#4fc2b9;--accent-bg:#17302d;
--s-todo:#9aa7a3;--s-todo-bg:#27302d;--s-building:#7fb0f5;--s-building-bg:#18273d;--s-review:#bf9cf0;--s-review-bg:#2a2038;--s-verified:#67d391;--s-verified-bg:#173025;
--s-waiting:#e2b94d;--s-waiting-bg:#352c12;--s-needs:#ff8a80;--s-needs-bg:#3a1a17;--s-cond:#9db3d1;--s-cond-bg:#222c3a;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#121816;--surface:#1a2220;--ink:#e6ecea;--muted:#9aa7a3;--line:#2c3835;--accent:#4fc2b9;--accent-bg:#17302d;
--s-todo:#9aa7a3;--s-todo-bg:#27302d;--s-building:#7fb0f5;--s-building-bg:#18273d;--s-review:#bf9cf0;--s-review-bg:#2a2038;--s-verified:#67d391;--s-verified-bg:#173025;
--s-waiting:#e2b94d;--s-waiting-bg:#352c12;--s-needs:#ff8a80;--s-needs-bg:#3a1a17;--s-cond:#9db3d1;--s-cond-bg:#222c3a;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--font);font-size:14px;line-height:1.5;padding-inline:16px;padding-block:20px 48px}
#app{max-width:1080px;margin:0 auto}
h1{font-size:26px;font-weight:600;margin:0;text-wrap:balance}
h2{font-size:17px;font-weight:600;margin:0;text-wrap:balance}
.top{display:flex;gap:12px;justify-content:space-between;align-items:flex-start;flex-wrap:wrap}
.sub{color:var(--muted);font-size:12.5px}.intro{max-width:68ch;color:var(--muted);margin:6px 0 0}
button,select,input{font:inherit;color:var(--ink)}
.theme{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-top:14px}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--s-todo-bg);margin:10px 0 8px}
.bar i{display:block;height:100%}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid transparent;border-radius:99px;padding:2px 10px;font-size:12px;font-weight:500;cursor:pointer;background:var(--s-todo-bg);color:var(--s-todo)}
.chip b{font-family:var(--mono);font-weight:500}
.chip[aria-pressed="true"]{outline:2px solid var(--accent)}
.st-building{background:var(--s-building-bg);color:var(--s-building)}.st-review{background:var(--s-review-bg);color:var(--s-review)}.st-verified{background:var(--s-verified-bg);color:var(--s-verified)}
.st-waiting{background:var(--s-waiting-bg);color:var(--s-waiting)}.st-needs-you{background:var(--s-needs-bg);color:var(--s-needs)}.st-conditional{background:var(--s-cond-bg);color:var(--s-cond)}.st-todo{background:var(--s-todo-bg);color:var(--s-todo)}
.fill-todo{background:var(--s-todo)}.fill-building{background:var(--s-building)}.fill-review{background:var(--s-review)}.fill-verified{background:var(--s-verified)}.fill-waiting{background:var(--s-waiting)}.fill-needs-you{background:var(--s-needs)}.fill-conditional{background:var(--s-cond)}
.needs{border-color:var(--s-needs);background:var(--surface)}
.needs h2{color:var(--s-needs)}
.needs ul,.next ul{margin:8px 0 0;padding-left:18px}.needs li,.next li{margin:4px 0}
.fp{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-top:8px}
.fp div{border-radius:6px;padding:8px 10px;background:var(--s-todo-bg)}.fp b{display:block;font-family:var(--mono);font-size:20px;font-weight:500}
.fp .OVERCOME{background:var(--s-verified-bg);color:var(--s-verified)}.fp .MITIGATED{background:var(--s-building-bg);color:var(--s-building)}.fp .WATCH{background:var(--s-waiting-bg);color:var(--s-waiting)}.fp .PENDING{background:var(--s-needs-bg);color:var(--s-needs)}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:14px}
.filters select,.filters input{background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:5px 8px;min-width:0}
.filters input{flex:1 1 180px}
.wave{margin-top:22px}.wave-head{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;justify-content:space-between}
.wave .goal{color:var(--muted);font-size:13px;margin:2px 0 0;max-width:80ch}
.prog{font-family:var(--mono);font-size:12px;color:var(--muted)}
.act{background:var(--surface);border:1px solid var(--line);border-radius:8px;margin-top:8px}
.act summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:10px 12px}
.act summary::-webkit-details-marker{display:none}
.act summary:focus-visible,.chip:focus-visible,.theme:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.act[open] summary{border-bottom:1px solid var(--line)}
.aid{font-family:var(--mono);font-size:12px;color:var(--muted)}
.atitle{flex:1 1 280px;min-width:0;font-weight:500}
.badge{font-size:11.5px;border:1px solid var(--line);border-radius:4px;padding:0 6px;color:var(--muted);white-space:nowrap}
.cost{font-family:var(--mono);font-size:12px;color:var(--muted)}
.body{padding:10px 14px 14px;display:grid;gap:8px;min-width:0}
.body p{margin:0;max-width:78ch}.lbl{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);display:block}
.ask{color:var(--s-needs);font-weight:500}
.tags{display:flex;flex-wrap:wrap;gap:6px}.tag{font-family:var(--mono);font-size:12px;border-radius:4px;padding:0 6px;background:var(--s-todo-bg);color:var(--s-todo)}
.tag.OVERCOME{background:var(--s-verified-bg);color:var(--s-verified)}.tag.MITIGATED{background:var(--s-building-bg);color:var(--s-building)}.tag.WATCH{background:var(--s-waiting-bg);color:var(--s-waiting)}.tag.PENDING{background:var(--s-needs-bg);color:var(--s-needs)}
.ev{margin:0;padding-left:18px;font-family:var(--mono);font-size:12px;overflow-wrap:anywhere}
.empty{color:var(--muted);padding:12px 0}
@media (max-width:560px){.fp{grid-template-columns:repeat(2,minmax(0,1fr))}h1{font-size:22px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div id="app"></div>
<script>
const D=/*DATA*/null;
const STATES=[["needs-you","Needs you"],["building","Building"],["review","In review"],["waiting","Waiting"],["conditional","Conditional"],["todo","To do"],["verified","Verified"]];
const SL=Object.fromEntries(STATES);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let F={wave:'',step:'',owner:'',state:'',q:''};
try{const s=JSON.parse(localStorage.getItem('cfp-control-filters')||'null');if(s)F=Object.assign(F,s);}catch(e){}
function save(){try{localStorage.setItem('cfp-control-filters',JSON.stringify(F));}catch(e){}}
const vis=a=>(!F.wave||a.wave===F.wave)&&(!F.step||a.step===F.step)&&(!F.owner||a.owner===F.owner)&&(!F.state||a.state===F.state)&&(!F.q||(a.id+' '+a.title+' '+a.detail+' '+(a.closes||[]).join(' ')).toLowerCase().includes(F.q.toLowerCase()));
function bar(list){const n=list.length||1;return `<div class="bar" role="img" aria-label="progress">${STATES.map(([k])=>{const c=list.filter(a=>a.state===k).length;return c?`<i class="fill-${k}" style="width:${100*c/n}%" title="${SL[k]}: ${c}"></i>`:''}).join('')}</div>`}
function row(a){
  const closes=(a.closes||[]).map(c=>`<span class="tag ${esc(D.fp[c]||'')}" title="${esc(c)}: ${esc(D.fp[c]||'')}">${esc(c)} ${esc(D.fp[c]||'')}</span>`).join('');
  const ev=(a.evidence||[]).length?`<span class="lbl">Evidence</span><ul class="ev">${a.evidence.map(e=>`<li>${esc(e)}</li>`).join('')}</ul>`:'';
  return `<details class="act" id="${esc(a.id)}"><summary><span class="chip st-${esc(a.state)}">${esc(SL[a.state])}</span><span class="aid">${esc(a.id)}</span><span class="atitle">${esc(a.title)}</span>
  <span class="badge" title="${esc(D.steps[a.step])}">${esc(a.step)}</span><span class="badge">${esc(D.owners[a.owner])}</span><span class="cost">${esc(a.cost)}</span></summary>
  <div class="body"><p>${esc(a.detail)}</p>${a.needs_you?`<p class="ask">${esc(a.needs_you)}</p>`:''}
  <div><span class="lbl">Done when</span><p>${esc(a.acceptance)}</p></div>
  ${closes?`<div><span class="lbl">Closes failure points</span><div class="tags">${closes}</div></div>`:''}
  ${(a.depends||[]).length?`<div><span class="lbl">After</span><div class="tags">${a.depends.map(d=>`<a class="tag" href="#${esc(d)}">${esc(d)}</a>`).join('')}</div></div>`:''}
  ${a.due?`<div><span class="lbl">Due</span><p>${esc(a.due)}</p></div>`:''}${ev}<span class="sub">Step ${esc(a.step)}: ${esc(D.steps[a.step])}. Updated ${esc(a.updated)}.</span></div></details>`}
function render(){
  const all=D.actions,c=k=>all.filter(a=>a.state===k).length;
  const needs=all.filter(a=>a.state==='needs-you');
  const due=all.filter(a=>a.state==='waiting'&&a.due).sort((a,b)=>a.due.localeCompare(b.due)).slice(0,4);
  const fpc=s=>Object.values(D.fp).filter(x=>x===s).length;
  const sel=(k,label,opts)=>`<select id="f-${k}" aria-label="${label}"><option value="">${label}: all</option>${opts.map(([v,t])=>`<option value="${esc(v)}"${F[k]===v?' selected':''}>${esc(t)}</option>`).join('')}</select>`;
  document.getElementById('app').innerHTML=`
  <div class="top"><div><h1>${esc(D.title)}</h1><div class="sub">as of ${esc(D.as_of)}</div><p class="intro">${esc(D.intro)}</p></div><button class="theme" id="tg" type="button">Theme</button></div>
  <section class="panel"><h2>${c('verified')} of ${all.length} actions verified</h2>${bar(all)}
    <div class="chips">${STATES.map(([k,t])=>`<button class="chip st-${k}" type="button" data-state="${k}" aria-pressed="${F.state===k}">${t} <b>${c(k)}</b></button>`).join('')}</div></section>
  ${needs.length?`<section class="panel needs"><h2>Needs you</h2><ul>${needs.map(a=>`<li><b>${esc(a.id)}</b> ${esc(a.title)}. <span class="ask">${esc(a.needs_you)}</span></li>`).join('')}</ul></section>`:`<section class="panel"><h2>Needs you</h2><p class="sub">Nothing is waiting on you.</p></section>`}
  ${due.length?`<section class="panel next"><h2>Coming up</h2><ul>${due.map(a=>`<li><b>${esc(a.due)}</b> ${esc(a.id)} ${esc(a.title)}</li>`).join('')}</ul></section>`:''}
  <section class="panel"><h2>Failure-point register</h2><div class="sub">${Object.keys(D.fp).length} root causes. An action's verification moves them.</div>
    <div class="fp">${['OVERCOME','MITIGATED','WATCH','PENDING'].map(s=>`<div class="${s}"><b>${fpc(s)}</b>${s.charAt(0)+s.slice(1).toLowerCase()}</div>`).join('')}</div></section>
  <div class="filters">${sel('wave','Wave',D.waves.map(w=>[w.id,w.id+' '+w.name]))}${sel('step','Step',Object.entries(D.steps).map(([k,v])=>[k,k+' '+v]))}${sel('owner','Owner',Object.entries(D.owners))}${sel('state','State',STATES)}
    <input id="f-q" type="search" placeholder="Search actions" aria-label="Search actions" value="${esc(F.q)}"><button class="theme" id="reset" type="button">Reset</button></div>
  ${D.waves.map(w=>{const mine=all.filter(a=>a.wave===w.id),shown=mine.filter(vis);if(!shown.length&&(F.wave||F.step||F.owner||F.state||F.q))return '';
    return `<section class="wave"><div class="wave-head"><h2>${esc(w.id)}. ${esc(w.name)}</h2><span class="prog">${mine.filter(a=>a.state==='verified').length} of ${mine.length} verified</span></div><p class="goal">${esc(w.goal)}</p>${bar(mine)}${shown.map(row).join('')||'<div class="empty">No actions match.</div>'}</section>`}).join('')}`;
  document.querySelectorAll('[data-state]').forEach(b=>b.onclick=()=>{F.state=F.state===b.dataset.state?'':b.dataset.state;save();render()});
  ['wave','step','owner','state'].forEach(k=>{document.getElementById('f-'+k).onchange=e=>{F[k]=e.target.value;save();render()}});
  const q=document.getElementById('f-q');q.oninput=e=>{F.q=e.target.value;save();const p=e.target.selectionStart;render();const n=document.getElementById('f-q');n.focus();n.setSelectionRange(p,p)};
  document.getElementById('reset').onclick=()=>{F={wave:'',step:'',owner:'',state:'',q:''};save();render()};
  document.getElementById('tg').onclick=()=>{const r=document.documentElement,dark=r.getAttribute('data-theme')==='dark'||(!r.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme:dark)').matches);r.setAttribute('data-theme',dark?'light':'dark')};
  if(location.hash){const t=document.getElementById(location.hash.slice(1));if(t&&t.tagName==='DETAILS')t.open=true;}
}
render();
</script>
'''


def build_html(d: dict, fp: dict) -> str:
    return TEMPLATE.replace("/*DATA*/null", json.dumps(page_data(d, fp), ensure_ascii=False).replace("</", "<\\/"))


def write_all(d: dict, fp: dict) -> None:
    OUT.write_text(build_html(d, fp), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["render", "validate", "summary", "set", "verify"])
    ap.add_argument("action", nargs="?")
    ap.add_argument("--state")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--needs-you", default="")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    d, fp = load(), load(FP_DATA)
    errs = validate(d, fp)
    if errs and a.cmd != "validate":
        print("action_list.json is invalid:\n  " + "\n  ".join(errs))
        return 1
    if a.cmd == "validate":
        print("OK" if not errs else "\n".join(errs))
        return 1 if errs else 0
    if a.cmd == "summary":
        print(f"{d['as_of']}: " + ", ".join(f"{k} {v}" for k, v in counts(d).items() if v))
        return 0
    if a.cmd == "set":
        act = next((x for x in d["actions"] if x["id"] == a.action), None)
        if act is None:
            print(f"no action {a.action}")
            return 1
        if a.state:
            if a.state not in BUILDER_STATES:
                print(f"state must be one of {BUILDER_STATES} (verified is the reviewer's: use verify)")
                return 1
            act["state"] = a.state
        if a.evidence:
            act.setdefault("evidence", []).append(a.evidence)
        if a.needs_you:
            act["needs_you"] = a.needs_you
        act["updated"] = a.today
        d["as_of"] = a.today
        errs = validate(d, fp)
        if errs:
            print("\n".join(errs))
            return 1
        save(d)
    if a.cmd == "verify":
        changes = apply_verify(d, fp, a.action, a.evidence, a.today)
        d["as_of"] = a.today
        errs = validate(d, fp)
        if errs:
            print("\n".join(errs))
            return 1
        save(d)
        FP_DATA.write_text(json.dumps(fp, indent=2, ensure_ascii=False), encoding="utf-8")
        from scripts import failure_points_doc as fpd
        fpd.OUT.write_text(fpd.render(fp), encoding="utf-8")
        print("register: " + ("; ".join(changes) if changes else "no change"))
    write_all(d, fp)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
