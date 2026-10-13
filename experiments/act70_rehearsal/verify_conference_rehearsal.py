"""Rehearsal check for ACT-70 (read-only): given a rebuilt Conference page, list every Provisional row with what it shows, the fields blanked and why (from the sidecar), and confirm that
no value the gate named as wrong is visible on any Provisional row and that no Open or Upcoming row is past its deadline.

    python experiments/act70_rehearsal/verify_conference_rehearsal.py <page.html> <Markets dir> [YYYY-MM-DD]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import provisional_blank as pb                                              # noqa: E402
from scripts import provisional_rows as pr                                  # noqa: E402


def main() -> int:
    page, markets = Path(sys.argv[1]), Path(sys.argv[2])
    today = sys.argv[3] if len(sys.argv) > 3 else "2026-10-12"
    html = page.read_text(encoding="utf-8")
    data = json.JSONDecoder().raw_decode(html[html.index("const DATA = ") + len("const DATA = "):])[0]
    side = json.loads(page.with_suffix(".provisional.json").read_text(encoding="utf-8"))
    rep = {e["name"]: e for e in side["rows"]}
    prov = [d for d in data if d["prov"]]
    print(f"{len(data)} rows on the page, {len(prov)} Provisional")
    # every value a gate failure named, for the market of each row
    bad_by_name: dict[str, list[str]] = {}
    for market in ("Cybersecurity", "Utility"):
        raw_path, _ = pr.find_raw(markets, market, __import__("datetime").date.fromisoformat(today))
        if raw_path is None:
            continue
        raw = pr.read_csv(raw_path)
        fails, _notes = pb.collect_failures(markets, market, raw_path, ROOT / "experiments" / "act70_rehearsal" / "work" / "data")
        for f in fails:
            for i in pb.match_rows(f, raw, None) if not f["canon"] else []:
                name = pr.tidy(raw[i].get("CONFERENCE"))
                vals = re.findall(r"=\s*'([^']{3,})'", f["text"]) + re.findall(r"https?://[^\s'\")]+", f["text"]) + re.findall(r'"([^"]{6,})"', f["text"])
                if f["check"] == "4" and ":" in f["text"]:
                    vals.append(f["text"].split(":", 1)[1].strip()[:60])
                bad_by_name.setdefault(name, []).extend(v for v in vals if v)
    problems = 0
    for d in prov:
        e = rep.get(d["n"], {})
        # the free-text prose (det) legitimately names the event's own venue; the fields the gate judged are the place, the dates, the deadline, the quote and the links
        shown = json.dumps({k: v for k, v in d.items() if k != "det"}, ensure_ascii=False)
        leaks = [v for v in bad_by_name.get(d["n"], []) if v and v in shown]
        past = d["s"] in ("Open", "Upcoming") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["dl"] or "") and d["dl"] < today
        problems += bool(leaks) + bool(past)
        print(f"- {d['n']} [{d['m']}] status={d['s']!r} deadline={d['dl'] or '(blank)'!r} place={d['loc'] or '(blank)'!r} details={'(blank)' if not d['det'] else d['det'][:30]!r}"
              f" submit={'(blank)' if not d['sub'] else 'shown'} evidence={'(blank)' if not d['ev'] else 'shown'}")
        print(f"    blanked: {', '.join(e.get('blanked') or []) or 'nothing'}; checked by the gate: {e.get('checked')}; why: {' | '.join(e.get('why') or [])[:200]}")
        if leaks:
            print(f"    !! KNOWN-BAD VALUE STILL VISIBLE: {leaks}")
        if past:
            print("    !! OPEN ROW PAST ITS DEADLINE")
    open_past = [d for d in data if d["s"] in ("Open", "Upcoming") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["dl"] or "") and d["dl"] < today]
    print(f"Open or Upcoming rows past their deadline on the whole page: {len(open_past)}" + ("".join(f"{chr(10)}  {d['n']} {d['dl']}" for d in open_past)))
    print(f"known-bad values visible on Provisional rows or open-past-deadline Provisional rows: {problems}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
