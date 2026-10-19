"""A compact reading digest of the collected pages, so a PERSON can label 'how does a company get a speaking slot here, and must it pay?' (2026-10-19, read-only).

    python experiments/sponsor_reader/digest.py <collect-dir> [first last]

For every event prints the page kinds and sizes, then the sentences that mention speaking, presenting, keynotes, panels, sessions, slots, sponsoring, exhibiting, a call for speakers or a submission, with a little context,
deduplicated, per page kind. Nothing is interpreted: the reader decides."""
import json
import re
import sys
from pathlib import Path

KEY = re.compile(r"(speak|present(?:er|ation|ing)|keynote|panel|fireside|session|slot|sponsor|exhibit|call for|call-for|cfp|submit|abstract|proposal|nominat|apply|invite|by invitation|pay|fee|free of charge|no cost|complimentary)", re.I)


def sentences(text: str):
    t = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\s{2,}| \| | - ", t) if 25 <= len(s.strip()) <= 320]


def digest(rec: dict, per_page: int = 6, cap: int = 2600) -> str:
    out, used = [], 0
    for p in rec["pages"]:
        sents, seen = [], set()
        for s in sentences(p["text"]):
            if KEY.search(s) and s.lower() not in seen and (re.search(r"speak|present|keynote|panel|session|slot|call for|call-for|cfp|submit|abstract|proposal|fireside", s, re.I)):
                seen.add(s.lower())
                sents.append(s)
        head = f"  [{p['kind']}] {p['url'][:90]} ({len(p['text'])} chars)"
        if not p["text"].strip():
            out.append(head + " UNREADABLE")
            continue
        out.append(head)
        for s in sents[:per_page]:
            if used + len(s) > cap:
                break
            out.append("     - " + s[:300])
            used += len(s)
    return "\n".join(out)


if __name__ == "__main__":
    d = Path(sys.argv[1]) / "pages"
    files = sorted(d.glob("*.json"))
    lo, hi = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 10 ** 6)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for f in files:
        i = int(f.stem)
        if not lo <= i <= hi:
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        print(f"\n### {i:03d} {rec['name']}  | upstream: {rec['ours']} | cost text: {str(rec.get('cost',''))[:110]}")
        print(digest(rec) if rec["pages"] else f"  (no pages: {rec.get('skipped','')})")
