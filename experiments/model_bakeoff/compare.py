"""ACT-56 compare tool: reads registry.jsonl (read-only) and prints, per fact, every model's answer side by side with the key and the verdict, then a per-model summary
(precision, wrong-accepted, found rate, stability across runs, cost, latency). Computes the second-opinion agreement between any two models. No model call happens here.

    python experiments/model_bakeoff/compare.py                          # every model, every run
    python experiments/model_bakeoff/compare.py --models ds,nemo         # a set of models
    python experiments/model_bakeoff/compare.py --runs ds-20261006-1,luna-20261006-1   # any set of runs
    python experiments/model_bakeoff/compare.py --second-opinion ds luna # agreement of two models, computed by our code
    python experiments/model_bakeoff/compare.py --no-facts               # summary only"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.model_bakeoff import registry as R               # noqa: E402


def select(rows: list[dict], models: list[str] | None = None, runs: list[str] | None = None) -> list[dict]:
    return [r for r in rows if (not models or r["model_key"] in models) and (not runs or r["run_id"] in runs)]


def summarise(rows: list[dict]) -> dict:
    """Per model: precision (correct / accepted, over scored facts), wrong-accepted, found rate (correct / facts the key has), stability (found in every run vs any run), cost, latency."""
    out = {}
    for m in sorted({r["model_key"] for r in rows}):
        mr = [r for r in rows if r["model_key"] == m and r["verdict"] != "call-failed"]
        runs = sorted({r["run_id"] for r in mr})
        accepted = [r for r in mr if r["accepted"]]
        correct = [r for r in mr if r["verdict"] == "correct"]
        wrong = [r for r in mr if r["verdict"] == "wrong-accepted"]
        with_key = [r for r in mr if r["key_value"]]
        keyed = {}
        for r in with_key:
            keyed.setdefault((r["job"], r["fact"]), {})[r["run_id"]] = r["verdict"] == "correct"
        calls = {(r["run_id"], r["job"]): r for r in rows if r["model_key"] == m}                      # one per call (facts of a call share cost and latency)
        out[m] = {"model_id": mr[0]["model_id"] if mr else "", "route": mr[0]["route"] if mr else "", "runs": len(runs), "facts_scored": len(mr),
                  "precision": round(len(correct) / len(accepted), 3) if accepted else None, "wrong_accepted": len(wrong),
                  "found": f"{len(correct)} of {len(with_key)}" if len(runs) <= 1 else f"{round(len(correct) / len(runs), 1)} of {round(len(with_key) / len(runs), 1)} per run",
                  "found_rate": round(len(correct) / len(with_key), 3) if with_key else None,
                  "stable_every_run": sum(1 for v in keyed.values() if len(v) == len(runs) and all(v.values())), "found_any_run": sum(1 for v in keyed.values() if any(v.values())), "key_facts": len(keyed),
                  "calls": len(calls), "failed_calls": len({(r["run_id"], r["job"]) for r in rows if r["model_key"] == m and r["verdict"] == "call-failed"}),
                  "cost_usd": round(sum((c.get("cost_usd") or 0.0) for c in calls.values()), 5),
                  "cost_per_call": round(sum((c.get("cost_usd") or 0.0) for c in calls.values()) / len(calls), 6) if calls else None,
                  "mean_latency_s": round(sum((c.get("latency_s") or 0.0) for c in calls.values()) / len(calls), 1) if calls else None,
                  "tokens_total": sum((c.get("tokens_total") or 0) for c in calls.values())}
    return out


def second_opinion(rows: list[dict], a: str, b: str) -> dict:
    """Two models answered the SAME page and question separately and blind. Agreement is computed here. Facts are matched per (job, fact), using each model's first run."""
    def first(m):
        mr = [r for r in rows if r["model_key"] == m and r["verdict"] != "call-failed"]
        if not mr:
            return {}
        rid = sorted({r["run_id"] for r in mr})[0]
        return {(r["job"], r["fact"]): r for r in mr if r["run_id"] == rid}
    ra, rb = first(a), first(b)
    out = {"compared": 0, "agree": 0, "agree_wrong": 0, "conflict": 0, "only_a": 0, "only_b": 0, "neither": 0, "a_wrong": 0, "a_wrong_caught_by_b": 0}
    for k, x in ra.items():
        y = rb.get(k)
        if y is None:
            continue
        out["compared"] += 1
        aw = x["verdict"] == "wrong-accepted"
        out["a_wrong"] += aw
        if x["accepted"] and y["accepted"]:
            if x["accepted"].strip().lower() == y["accepted"].strip().lower():
                out["agree"] += 1
                out["agree_wrong"] += aw
            else:
                out["conflict"] += 1
                out["a_wrong_caught_by_b"] += aw
        elif x["accepted"]:
            out["only_a"] += 1
            out["a_wrong_caught_by_b"] += aw
        elif y["accepted"]:
            out["only_b"] += 1
        else:
            out["neither"] += 1
    return out


def per_fact(rows: list[dict]) -> list[str]:
    models = sorted({r["model_key"] for r in rows})
    by = {}
    for r in rows:
        by.setdefault((r["event"], r["fact"], r["key_value"]), {}).setdefault(r["model_key"], []).append(r)
    lines = []
    for (ev, fact, key), per in sorted(by.items()):
        lines.append(f"{ev[:55]} | {fact} | KEY={key!r}")
        for m in models:
            for r in per.get(m, []):
                lines.append(f"    {m:7s} {r['run_id'][-12:]:12s} accepted={r['accepted']!r:24s} verdict={r['verdict']:14s} verbatim={r['quote_verbatim_on_page']!s:5s} ({r['accept_why'][:50]})")
    return lines


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--runs", default="")
    ap.add_argument("--no-facts", action="store_true")
    ap.add_argument("--second-opinion", nargs=2, metavar=("A", "B"))
    ap.add_argument("--registry", default="")
    a = ap.parse_args(argv)
    rows = R.read(Path(a.registry) if a.registry else None)
    rows = select(rows, [m for m in a.models.split(",") if m], [r for r in a.runs.split(",") if r])
    if not rows:
        print("no rows"); return
    if not a.no_facts:
        print("\n".join(per_fact(rows)))
    print("\nPER-MODEL SUMMARY")
    for m, s in summarise(rows).items():
        print(f"  {m:7s} {s['model_id']} [{s['route']}] runs={s['runs']} precision={s['precision']} wrong_accepted={s['wrong_accepted']} found={s['found']} (rate {s['found_rate']}) "
              f"stable_every_run={s['stable_every_run']}/{s['key_facts']} found_any_run={s['found_any_run']} calls={s['calls']} failed={s['failed_calls']} cost=${s['cost_usd']} "
              f"(${s['cost_per_call']}/call) latency={s['mean_latency_s']}s codex_tokens={s['tokens_total']}")
    if a.second_opinion:
        print(f"\nSECOND OPINION {a.second_opinion[0]} vs {a.second_opinion[1]}: {second_opinion(rows, *a.second_opinion)}")


if __name__ == "__main__":
    main()
