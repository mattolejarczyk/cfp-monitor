"""Measure verify.find_date against the saved page library: stored deadline + its cited page, offline.

    python experiments/purpose_audit/find_date_corpus.py --label before > before.json
    python experiments/purpose_audit/find_date_corpus.py --label after  > after.json

For every stored deadline (conference and award tables) whose cited evidence URL is in page_library/page_library.db,
record whether find_date(page text, deadline) is True. No network. Compare the two JSON files to see exactly which
rows gained or lost a hit."""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor import verify  # noqa: E402

DB = Path.home() / "AppData" / "Local" / "CFP-Monitor" / "cfp_monitor.db"
LIB = ROOT / "page_library" / "page_library.db"


def main() -> None:
    label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else "run"
    lib = sqlite3.connect(LIB)
    pages = {u: t for u, t in lib.execute("select url, text from pages where text is not null and text != ''")}
    con = sqlite3.connect(DB)
    out = []
    for table in ("grounding_facts", "award_grounding_facts"):
        for eid, name, dl, url in con.execute(
                f"select event_id, name, deadline, deadline_evidence_url from {table} "
                "where deadline != '' and deadline_evidence_url != ''"):
            text = pages.get(url)
            if text is None:
                continue
            try:
                d = date.fromisoformat(dl)
            except ValueError:
                continue
            out.append({"table": table, "event_id": eid, "name": name, "deadline": dl, "url": url,
                        "hit": verify.find_date(text, d)})
    json.dump({"label": label, "rows": out, "compared": len(out), "hits": sum(r["hit"] for r in out)}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
