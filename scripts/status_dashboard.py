"""Build the CFP status board (one HTML page) from docs/design/status.json.

   python scripts/status_dashboard.py [--out PATH]

The data file is the single source: every number on the page is typed there with its source file named, so a wrong number is traced to one line.
Update status.json in the same commit as the work that changes a number; then regenerate and republish the page. Every update must also rewrite `working_on`, set `now_updated` = `as_of`, and date each waiting item (`added`); stale ones are warned about on the page and on stderr. Default output: dashboard/status.html (git-ignored).
Read-only apart from the output file; no database, no network.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "design" / "status.json"
TEMPLATE = ROOT / "scripts" / "status_template.html"


def freshness_warnings(data, max_age_days=2):
    """The board must not go stale quietly (operator, 2026-10-02: 'Working on' and 'Waiting on you' were not being updated).
    Every update must rewrite `working_on`, stamp `now_updated` with the same date as `as_of`, and date every waiting item (`added`).
    A waiting item older than `max_age_days` is flagged: either it is still open and the age says so, or it is done and should be removed."""
    from datetime import date
    warns, today = [], date.fromisoformat(data["as_of"])
    if data.get("now_updated") != data["as_of"]:
        warns.append(f"'Working on' was last updated {data.get('now_updated') or 'never'}, board is as of {data['as_of']}: rewrite it")
    if not data.get("working_on"):
        warns.append("'Working on' has no items")
    for d in data["decisions"]:
        if not d.get("added"):
            warns.append(f"waiting item has no date: {d['text'][:60]}")
        elif (today - date.fromisoformat(d["added"])).days > max_age_days:
            warns.append(f"waiting item is {(today - date.fromisoformat(d['added'])).days} days old, remove it if done: {d['text'][:60]}")
    return warns


def build(out):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for h in data["headline"].values():                       # the bar must add up: refuse to render a wrong total
        assert sum(l["n"] for l in h["levels"]) == h["rows"], f"{h['label']}: levels do not add to {h['rows']}"
    data["warnings"] = freshness_warnings(data)
    for w in data["warnings"]:
        print("WARNING:", w, file=sys.stderr)
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "dashboard" / "status.html"
    print(build(out))
