"""Score the whole-page reader's saved library answers against the locked benchmark key. Offline, free, no model calls.

    python experiments/whole_page_reader/score_vs_key.py [--json out.json]

INPUTS  experiments/whole_page_reader/library_results.json   accepted submission dates per page (code-gated, 10-01 run)
        docs/agents/results/01-benchmark-key.csv             the key (40 events; checksum in the .sha256 beside it)
        docs/agents/inputs/benchmark_events.csv              event_home_url for each id
        page_library/page_library.db                          which hosts the library holds

HOW AN EVENT IS SCORED (stated so the number is not over-read)
  Pages are matched to an event by HOST (the home URL's host, www. removed). An event whose host has no page in the
  library is NOT SCORED: the reader never saw it.
  Key row WITH a deadline   HIT   the key date is among the dates the reader accepted on that host's pages
                            WRONG the reader accepted dates on that host, none equal to the key date
                            MISS  the reader accepted nothing on that host
  Key row WITHOUT a deadline  CLEAN    the reader accepted no date on or after the run date (2026-10-01)
                              CHECK    the reader accepted a date ahead; listed for a person: it may be a real call the key
                                       missed (the edition problem), or a false positive. NOT counted as an error.
  The reader runs on whatever pages the library holds for a host, not the specific page the key cites, and the library
  pages are the 10-01 fetch. This measures what the reader could say, on the same pages, against what the key says.
"""
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUN_DATE = "2026-10-01"


def host_of(url: str) -> str:
    s = (url or "").lower().strip().split("://", 1)[-1].split("/", 1)[0]
    return s[4:] if s.startswith("www.") else s


def score(key_rows: list[dict], home_urls: dict[str, str], results: dict, library_hosts: set[str]) -> dict:
    accepted: dict[str, set[str]] = {}
    for url, r in results.items():
        h = host_of(r.get("host") or url)
        for a in r.get("accepted", []):
            accepted.setdefault(h, set()).add(a["date"])
    out = {"HIT": [], "WRONG": [], "MISS": [], "CLEAN": [], "CHECK": [], "NOT_SCORED": []}
    for k in key_rows:
        eid, name, deadline = k["id"], k["event_name"], (k["submission_deadline"] or "").strip()
        h = host_of(home_urls.get(eid, ""))
        if h not in library_hosts:
            out["NOT_SCORED"].append({"id": eid, "name": name, "why": f"host {h} not in the library"})
            continue
        got = sorted(accepted.get(h, set()))
        if deadline:
            if deadline in got:
                out["HIT"].append({"id": eid, "name": name, "key": deadline})
            elif got:
                out["WRONG"].append({"id": eid, "name": name, "key": deadline, "reader": got[:6]})
            else:
                out["MISS"].append({"id": eid, "name": name, "key": deadline})
        else:
            ahead = [d for d in got if d >= RUN_DATE]
            (out["CHECK"] if ahead else out["CLEAN"]).append({"id": eid, "name": name, "key_status": k["call_status"], "reader_ahead": ahead[:6]})
    return out


def main() -> None:
    results = json.load(open(ROOT / "experiments/whole_page_reader/library_results.json", encoding="utf-8"))
    with open(ROOT / "docs/agents/results/01-benchmark-key.csv", encoding="utf-8", newline="") as fh:
        key = list(csv.DictReader(fh))
    with open(ROOT / "docs/agents/inputs/benchmark_events.csv", encoding="utf-8", newline="") as fh:
        homes = {r["id"]: r["event_home_url"] for r in csv.DictReader(fh)}
    con = sqlite3.connect(ROOT / "page_library/page_library.db")
    lib_hosts = {host_of(h) for (h,) in con.execute("select distinct host from pages")}
    s = score(key, homes, results, lib_hosts)
    scored = sum(len(v) for k, v in s.items() if k != "NOT_SCORED")
    with_dl = len(s["HIT"]) + len(s["WRONG"]) + len(s["MISS"])
    print(f"Scored {scored} of {len(key)} key events ({len(s['NOT_SCORED'])} not in the library).")
    print(f"Key rows with a deadline: {with_dl} scored -> HIT {len(s['HIT'])}, WRONG {len(s['WRONG'])}, MISS {len(s['MISS'])}")
    print(f"Key rows with no deadline: {len(s['CLEAN']) + len(s['CHECK'])} scored -> CLEAN {len(s['CLEAN'])}, CHECK (reader found a date ahead) {len(s['CHECK'])}")
    for label in ("WRONG", "MISS", "CHECK", "NOT_SCORED"):
        for r in s[label]:
            print(f"  {label}: {r['id']} {r['name'][:46]} | " + "; ".join(f"{k}={v}" for k, v in r.items() if k not in ("id", "name")))
    if "--json" in sys.argv:
        json.dump(s, open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
