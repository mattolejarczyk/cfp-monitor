"""ACT-56 runner. Step 1 (this file): ASK. Each job is sent to the model as a fresh blind single-turn request; the every call is scored in code AFTER it returns and appended to registry.jsonl (append-only).
Step 2 (compare.py): read the registry and compare models.

    python experiments/model_bakeoff/run_bakeoff.py --model nemo --repeats 3
    python experiments/model_bakeoff/run_bakeoff.py --model luna --limit 1          # prove the Codex wrapper on one call

Pages come from the cache of experiments/read_the_page_pass (the pages a person verified on); an event whose page the plain fetch cannot read is skipped (it would only test the fetcher).
Never run with a customer page or a credential: public web pages only. Stops at the first Codex error and prints it verbatim."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.model_bakeoff import bakeoff_lib as B            # noqa: E402
from experiments.model_bakeoff import registry as R               # noqa: E402
from experiments.read_the_page_pass import pass_lib as L          # noqa: E402

PAGES = ROOT / "experiments" / "read_the_page_pass" / "pages.json"


def build_jobs() -> list[dict]:
    """Reader jobs: every person-confirmed pinned event whose page is readable; the trap fixtures; and, for events with a person-confirmed deadline, the deadline question."""
    from experiments.finder_reader_test.run import SYSTEM as DEADLINE_SYSTEM
    from scripts.pinned_rows import load_pins
    cache = json.loads(PAGES.read_text(encoding="utf-8")) if PAGES.exists() else {}
    confirmed = B.person_confirmed_events()
    jobs, seen = [], set()
    gold = L.gold_facts(load_pins())
    by_event = {}
    for g in gold:
        by_event.setdefault(g["canonical"], []).append(g)
    pin_by = {p["canonical"]: p for p in load_pins()}
    for cid, facts in by_event.items():
        p = pin_by[cid]
        if cid not in confirmed:
            continue                                                       # reader is scored ONLY on the person-confirmed tier
        text = "\n\n".join(cache.get(u, "")[:7000] for u in p.get("links", []) if cache.get(u))
        if not text.strip():
            continue
        jid = f"read::{p['event'][:40]}::{cid}"
        if jid in seen:
            continue
        seen.add(jid)
        jobs.append({"id": jid, "kind": "read", "event": p["event"], "edition": B.edition_of(cid), "text": text, "system": L.SYSTEM,
                     "facts": [{"field": f["field"], "gold": f["gold"]} for f in facts]})
        dl = str(p["set"].get("SUBMISSION DEADLINE", "")).strip()
        if dl:
            jobs.append({"id": f"deadline::{cid}", "kind": "deadline", "event": p["event"], "edition": B.edition_of(cid), "text": text, "system": DEADLINE_SYSTEM,
                         "facts": [{"field": "deadline", "gold": dl}]})
    traps = {c["id"]: c for c in json.load(open(ROOT / "docs" / "qa" / "trap-cases.json", encoding="utf-8"))["cases"]}
    for tid, ed, gold_v, label in (("T01", "2026", "", "TRAP T01 Carbon Capture Technology Expo MENA, asked 2026 (page shows 2027): must stay blank"),
                                   ("T02", "2027", "2027-05-10", "TRAP T02 ODSC East two editions, asked 2027"),
                                   ("T02", "2026", "2026-04-28", "TRAP T02 ODSC East two editions, asked 2026"),
                                   ("T09", "2027", "2027-01-26", "TRAP T09 European CCUS 2027")):
        jobs.append({"id": f"trap::{tid}::{ed}", "kind": "read", "event": label, "edition": ed, "text": traps[tid]["fixture"], "system": L.SYSTEM,
                     "facts": [{"field": "start_date", "gold": gold_v}]})
    return jobs


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="a key from models.json")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="only the first N jobs (to prove a wrapper)")
    ap.add_argument("--kinds", default="read,deadline", help="comma list of job kinds")
    ap.add_argument("--first-run", type=int, default=1, help="number the first repeat from this (to add runs later)")
    ap.add_argument("--run-prefix", default="", help="run id prefix (default <model>-<date>)")
    a = ap.parse_args()
    if a.model not in B.load_models():
        sys.exit(f"unknown model {a.model}: add it to experiments/model_bakeoff/models.json")
    jobs = [j for j in build_jobs() if j["kind"] in a.kinds.split(",")]
    if a.limit:
        jobs = jobs[:a.limit]
    prefix = a.run_prefix or f"{a.model}-{date.today().strftime('%Y%m%d')}"
    print(f"{len(jobs)} jobs, model {a.model} = {B.load_models()[a.model]['id']}", flush=True)
    for rep in range(a.first_run, a.first_run + a.repeats):
        run_id = f"{prefix}-{rep}"
        done = {r["job"] for r in R.read() if r["run_id"] == run_id}        # resume: a job already in the registry for this run is not asked again
        run_usd = [0.0]
        for j in jobs:
            if j["id"] in done:
                continue
            msgs = B.blind_messages(j["system"], j["event"], j["edition"], j["text"])
            try:
                r = B.ask(a.model, msgs, f"{run_id}:{j['id'][:50]}", run_usd=run_usd)
            except B.CodexError as e:
                print("\nCODEX ERROR (exact text, stopping, no retry):\n" + str(e), flush=True)
                sys.exit(3)
            rows = R.append_rows(a.model, run_id, j, msgs, r)
            print(f"  {run_id} {j['id'][:50]}: status {r['status']} {r['seconds']}s cost {r['cost']} verdicts {[x['verdict'] for x in rows]}", flush=True)
            if r["error"] == "budget cap reached":
                print("BUDGET CAP: stopping"); return
        print(f"{run_id} done, OpenRouter spend this run {run_usd[0]:.4f} USD, total logged {B.spent_usd():.4f} USD", flush=True)


if __name__ == "__main__":
    main()
