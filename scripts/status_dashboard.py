"""Build the CFP status board (one HTML page) from docs/design/status.json.

   python scripts/status_dashboard.py [--out PATH]

The data file is the single source: every number on the page is typed there with its source file named, so a wrong number is traced to one line.
Update status.json in the same commit as the work that changes a number; then regenerate and republish the page. Default output: dashboard/status.html (git-ignored).
Read-only apart from the output file; no database, no network.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "design" / "status.json"
TEMPLATE = ROOT / "scripts" / "status_template.html"


def build(out):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    for h in data["headline"].values():                       # the bar must add up: refuse to render a wrong total
        assert sum(l["n"] for l in h["levels"]) == h["rows"], f"{h['label']}: levels do not add to {h['rows']}"
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", json.dumps(data).replace("</", "<\\/"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT / "dashboard" / "status.html"
    print(build(out))
