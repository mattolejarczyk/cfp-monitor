"""Build the CFP status board (one HTML page) from docs/design/status.json.

   python scripts/status_dashboard.py [--out PATH]

The data file is the single source: every number on the page is typed there with its source file named, so a wrong number is traced to one line.
Update status.json in the same commit as the work that changes a number; then regenerate and republish the page. Every update must also rewrite `working_on`, set `now_updated` = `as_of`, and date each waiting item (`added`); stale ones are warned about on the page and on stderr. Default output: dashboard/status.html (git-ignored).
Read-only apart from the output file; no database, no network.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


_LABELS = {"START DATE": "start date", "CONFERENCE DATES": "dates", "SUBMISSION DEADLINE": "deadline", "CFP_SUBMISSION_URL": "submission link", "LOCATION": "location",
           "CITY": "city", "COUNTRY": "country", "ORGANIZER": "organizer", "FORMAT": "format", "MAIN_INFO_URL": "main page", "STATUS DETAILS": "details"}


def verified_by_operator() -> list[dict]:
    """Everything a person verified on the event's own page, from docs/operations/pinned_rows.json (the file the weekly load enforces), so the board and the load cannot drift."""
    try:
        from scripts.pinned_rows import load_pins
        pins = load_pins()
    except Exception:                                                        # noqa: BLE001
        return []
    out = []
    for p in pins:
        parts = []
        for k, v in p.get("set", {}).items():
            if k in ("DEADLINE_EVIDENCE_URL", "DEADLINE_QUOTE", "IS_PROJECTED"):
                continue
            lab = _LABELS.get(k, k.lower())
            parts.append(f"{lab}: blank (the page states nothing)" if v == "" else (f"{lab} set" if k in ("STATUS DETAILS", "CFP_SUBMISSION_URL") else f"{lab}: {v}"))
        out.append({"event": p.get("event") or p["canonical"], "what": "; ".join(parts), "links": p.get("links", []), "on": p.get("ruled_on", ""), "until": p.get("until", "")})
    return sorted(out, key=lambda x: (x["on"], x["event"]), reverse=True)


def build(out):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for h in data["headline"].values():                       # the bar must add up: refuse to render a wrong total
        assert sum(l["n"] for l in h["levels"]) == h["rows"], f"{h['label']}: levels do not add to {h['rows']}"
    data["verified"] = verified_by_operator()
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
