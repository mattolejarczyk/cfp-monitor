"""Scores experiment T1 (and reads T2) AFTER every arm has answered: joins the arms' answers with key.json in code, fetches each cited page OURSELVES and
checks whether it states the date (experiments/sitemap_discovery/dates_v2.find_target on the fetched text; read_the_page_pass.run.page_text, plain fetch then
the real Chrome), and writes scores.csv and tables.md (the tables RESULT.md carries). No model call. The arms never saw the key.

    .venv/Scripts/python.exe experiments/research_path_bakeoff/score.py [--arms A B C D] [--no-fetch]

Per arm and row: deadline; equals_key (right / wrong / blank / no-key); page_states_date (yes / no / unreadable / no-url) from OUR fetch of the URL the arm
cited; quote_on_page (for arms that returned one); USD; seconds; searches. Totals, a split by key source (person-confirmed or customer-verified = hard key;
shipped = soft key, which favours arm A because the shipped value came from that path), and the agreement between arms."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, ROOT / "experiments" / "sitemap_discovery", ROOT / "experiments" / "sentence_picking"):
    sys.path.insert(0, str(p))
import os                                                              # noqa: E402
os.environ.setdefault("CFP_CDP_URL", "http://127.0.0.1:9222")         # before any cfp_monitor import: config reads it at import time (see arm_bcd.py)

ARM_FILES = {"A": "arm_a_serial.jsonl", "B": "arm_b.jsonl", "C": "arm_c.jsonl", "D": "arm_d.jsonl"}
ARM_URL = {"A": "evidence_url", "B": "url", "C": "url", "D": "url"}
ARM_NAME = {"A": "A grounded (current)", "B": "B search+fetch+extract+prove", "C": "C OpenAI web_search (via OpenRouter)", "D": "D Codex CLI --search"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    return {json.loads(l)["canonical"]: json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["A", "B", "C", "D"])
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    rows = json.loads((HERE / "rows.json").read_text(encoding="utf-8"))["rows"]
    key = json.loads((HERE / "key.json").read_text(encoding="utf-8"))
    arms = {k: load(HERE / ARM_FILES[k]) for k in a.arms}
    cache = json.loads((HERE / "pages_cache.json").read_text(encoding="utf-8")) if (HERE / "pages_cache.json").exists() else {}
    import dates_v2 as d2
    from experiments.read_the_page_pass import run as R
    R.LOG = HERE / "reader_llm_log.jsonl"
    out_rows = []
    for row in rows:
        c = row["canonical"]
        k = key[c]
        for arm in a.arms:
            r = arms[arm].get(c)
            if r is None:
                out_rows.append({"n": row["n"], "event": row["event"], "market": row["market"], "key_source": k["key_source"], "key": k["key"], "arm": arm, "answered": "no",
                                 "deadline": "", "equals_key": "not-run", "url": "", "page_states_date": "", "quote_on_page": "", "usd": 0, "secs": 0, "searches": 0})
                continue
            dl = (r.get("deadline") or "")[:10]
            if r.get("skipped") or r.get("error") and not dl and not r.get("url"):
                eq = "not-run" if r.get("skipped") else ("blank" if k["key"] else "no-key")
            elif not k["key"]:
                eq = "no-key"
            elif not dl:
                eq = "blank"
            else:
                eq = "right" if dl == k["key"] else "wrong"
            url = r.get(ARM_URL[arm]) or ""
            states, qop = "no-url", ""
            if url.startswith("http") and dl:
                if a.no_fetch:
                    states = "not-fetched"
                else:
                    try:
                        text = cache.get(url) or R.page_text(url, cache)
                    except Exception:                                # noqa: BLE001
                        text = ""
                    if not text.strip():
                        states = "unreadable"
                    else:
                        try:
                            hit = d2.find_target(text, date.fromisoformat(dl))
                        except ValueError:
                            hit = None
                        states = f"yes ({hit[0]})" if hit else "no"
                        q = r.get("quote") or ""
                        qop = ("yes" if norm(q) in norm(text) else "no") if q else ""
            elif url.startswith("http") and not dl:
                states = "no-date"
            out_rows.append({"n": row["n"], "event": row["event"], "market": row["market"], "key_source": k["key_source"], "key": k["key"], "arm": arm, "answered": "yes",
                             "deadline": dl, "equals_key": eq, "url": url, "page_states_date": states, "quote_on_page": qop,
                             "usd": round(float(r.get("usd") or 0) + float(r.get("usd_search") or 0) + float(r.get("usd_tokens_est") or 0), 5),
                             "secs": r.get("secs", 0), "searches": r.get("searches", 0) or 0, "error": (r.get("error") or r.get("skipped") or "")[:120]})
    (HERE / "pages_cache.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with open(HERE / "scores.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)

    # B's own cost: search + reader calls, from calls.jsonl (the row record carries the search part only)
    calls = [json.loads(l) for l in (HERE / "calls.jsonl").read_text(encoding="utf-8").splitlines()] if (HERE / "calls.jsonl").exists() else []
    usd_by_arm = Counter()
    for cl in calls:
        usd_by_arm[cl.get("arm")] += float(cl.get("usd") or 0)
    lines = ["## T1 totals (" + str(len(rows)) + " rows)", "", "| arm | answered | right | wrong | blank | no-key | cited page states the date (yes / no / unreadable / no URL) | quote on page (yes / no) | USD | searches | mean s | median s |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in a.arms:
        rs = [r for r in out_rows if r["arm"] == arm]
        ans = [r for r in rs if r["answered"] == "yes" and r["equals_key"] != "not-run"]
        eq = Counter(r["equals_key"] for r in ans)
        st = Counter(r["page_states_date"].split(" ")[0] for r in ans if r["deadline"])
        qp = Counter(r["quote_on_page"] for r in ans if r["quote_on_page"])
        secs = sorted(float(r["secs"] or 0) for r in ans)
        usd = usd_by_arm[arm] if arm in ("B", "C") else sum(r["usd"] for r in ans)
        lines.append(f"| {ARM_NAME[arm]} | {len(ans)} | {eq['right']} | {eq['wrong']} | {eq['blank']} | {eq['no-key']} | {st['yes']} / {st['no']} / {st['unreadable']} / {st['no-url']} | {qp['yes']} / {qp['no']} | "
                     f"{usd:.3f} | {sum(int(r['searches'] or 0) for r in ans)} | {sum(secs) / len(secs) if secs else 0:.0f} | {secs[len(secs) // 2] if secs else 0:.0f} |")
    lines += ["", "## By key source (hard = person-confirmed or customer-verified; soft = the shipped value, which came from the grounded path)", "",
              "| arm | hard: right / wrong / blank (n) | soft: right / wrong / blank (n) |", "|---|---|---|"]
    for arm in a.arms:
        parts = []
        for label, srcs in (("hard", ("person-confirmed", "customer-verified-agrees")), ("soft", ("shipped",))):
            rs = [r for r in out_rows if r["arm"] == arm and r["key_source"] in srcs and r["answered"] == "yes" and r["equals_key"] not in ("not-run", "no-key")]
            eq = Counter(r["equals_key"] for r in rs)
            parts.append(f"{eq['right']} / {eq['wrong']} / {eq['blank']} ({len(rs)})")
        lines.append(f"| {ARM_NAME[arm]} | {parts[0]} | {parts[1]} |")
    lines += ["", "## Agreement between arms (rows where both gave a date)", "", "| pair | both dated | agree | agree and right | agree and wrong | disagree: first right | second right | neither |", "|---|---|---|---|---|---|---|---|"]
    by = {(r["arm"], r["n"]): r for r in out_rows}
    for i, x in enumerate(a.arms):
        for y in a.arms[i + 1:]:
            both = [(by[(x, r["n"])], by[(y, r["n"])]) for r in rows if by.get((x, r["n"]), {}).get("deadline") and by.get((y, r["n"]), {}).get("deadline")]
            agree = [(p, q) for p, q in both if p["deadline"] == q["deadline"]]
            dis = [(p, q) for p, q in both if p["deadline"] != q["deadline"]]
            lines.append(f"| {x} vs {y} | {len(both)} | {len(agree)} | {sum(1 for p, _ in agree if p['equals_key'] == 'right')} | {sum(1 for p, _ in agree if p['equals_key'] == 'wrong')} | "
                         f"{sum(1 for p, _ in dis if p['equals_key'] == 'right')} | {sum(1 for _, q in dis if q['equals_key'] == 'right')} | {sum(1 for p, q in dis if p['equals_key'] != 'right' and q['equals_key'] != 'right')} |")
    lines += ["", "## Every row", "", "| # | event | key (source) | " + " | ".join(a.arms) + " |", "|---|---|---|" + "---|" * len(a.arms)]
    for r0 in rows:
        cells = []
        for arm in a.arms:
            r = by.get((arm, r0["n"]), {})
            mark = {"right": "RIGHT", "wrong": "WRONG", "blank": "blank", "no-key": "(no key)", "not-run": "not run"}.get(r.get("equals_key", "not-run"), "?")
            cells.append(f"{r.get('deadline') or '-'} {mark}; page {r.get('page_states_date') or '-'}")
        k = key[r0["canonical"]]
        lines.append(f"| {r0['n']} | {r0['event'][:45]} | {k['key'] or '(blank)'} ({k['key_source']}) | " + " | ".join(cells) + " |")
    (HERE / "tables.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"-> {HERE / 'scores.csv'}, {HERE / 'tables.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
