"""Check each awards deadline against the page it cites, and emit the page's checks CSV.

WHAT THIS IS FOR
`build_review_page.py --checks` wants four columns - EVENT_ID, CHECK, CHECK_URL, CHECK_QUOTE -
and refuses to build an evidence-bearing page without them. `audit_evidence.py` produces them
for conferences, but it reads the `evidence` table and joins `grounding_facts`, so it has
nothing to say about awards. This is the awards sibling.

THE KEY SPACE IS UPSTREAM'S, DELIBERATELY
The page is built from the delivery CSV, whose EVENT_ID column is upstream's. Our canonical id
would join to nothing there. So rows are read from the database - the system of record - and
emitted under `upstream_event_id`, which is exactly what that column was added for (5.4).

THREE VERDICTS, AND ONE WE REFUSE TO GUESS
    verified     we opened the cited page and its own words carry the deadline
    no_quote     the page loaded and does not carry that sentence
    unreadable   we could not open the page - a statement about US, not about the date

`contradicted` means the cited page states a DIFFERENT deadline, and it is the only verdict
that argues the date is wrong. Proving that needs more than noticing our sentence is absent: a
page can drop a quote, reword it, or move it behind a tab. So this pass never emits it. An
absent quote is reported as `no_quote`, which says what we actually know. 2.5 - decline rather
than guess - and `load_checks` already treats the last two as statements about our ability to
confirm rather than about the deadline.

A PASSED DEADLINE IS STILL CHECKED HERE
Amendments v1.4 and v2.2 exempt passed deadlines from the acceptance GATE, because a delivery
must not be rejected for expected decay. That is a rule about blocking, not about knowing.
This pass reports what it finds either way, and the page can show a reader that an old row's
evidence has gone - which is true and worth seeing.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

OUT_COLUMNS = ["EVENT_ID", "CHECK", "CHECK_URL", "CHECK_QUOTE"]


def _norm(s: str) -> str:
    """Whitespace-insensitive compare, the same shape the gate uses for criterion 3."""
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def claims(db: str) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select upstream_event_id, event_id, name, deadline, deadline_quote, "
        "deadline_evidence_url from award_grounding_facts "
        "where trim(coalesce(deadline_evidence_url,'')) != '' "
        "  and trim(coalesce(deadline_quote,'')) != '' "
        "order by name")]
    con.close()
    return rows


def verdicts(rows: list[dict], pages: dict[str, list[str]]) -> list[dict]:
    """`pages` maps a URL to EVERY rendering we managed to read of it.

    ONE PAGE, SEVERAL RENDERINGS, AND THEY DISAGREE. The first version of this pass read each
    page through the crawl4ai ladder alone and reported `no_quote` on 12 rows whose deadline
    was still ahead - including four the acceptance gate had verified hours earlier, and two
    quotes read off the page by hand the same afternoon. The gate was right.

    The cause is not the site: the ladder returns MARKDOWN, with link syntax and image alt text
    interleaved into the prose, while `verify.fetch_text` returns flat text - and citations are
    extracted and gate-checked against the flat rendering. A sentence that is plainly on the
    page fails a substring match against a rendering that has spliced `[label](href)` through
    the middle of it.

    So a quote found in ANY rendering counts. The question is whether the page carries the
    sentence, and a renderer that mangled it is our artefact, not the site's. Reporting
    `no_quote` because one reader garbled the text would put "Need to Verify" in front of a
    customer for a deadline we had confirmed twice.
    """
    out = []
    for r in rows:
        url = (r["deadline_evidence_url"] or "").strip()
        renderings = [t for t in pages.get(url, []) if t]
        quote = _norm(r["deadline_quote"])
        if not renderings:
            check = "unreadable"
        elif any(quote in _norm(t) for t in renderings):
            check = "verified"
        else:
            check = "no_quote"
        out.append({"EVENT_ID": r["upstream_event_id"] or r["event_id"],
                    "CHECK": check,
                    "CHECK_URL": url,
                    "CHECK_QUOTE": r["deadline_quote"] if check == "verified" else ""})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--limit", type=int, help="check only the first N distinct pages")
    ap.add_argument("--apply", action="store_true",
                    help="also write the verdicts back to award_grounding_facts.verify_state")
    a = ap.parse_args()

    rows = claims(a.db)
    urls = sorted({(r["deadline_evidence_url"] or "").strip() for r in rows})
    if a.limit:
        urls = urls[:a.limit]
        keep = set(urls)
        rows = [r for r in rows if (r["deadline_evidence_url"] or "").strip() in keep]

    print(f"{len(rows)} cited award deadline(s) across {len(urls)} page(s)")
    print("one visit per page; the ladder is climbed on failure\n")

    # THE GATE'S READER FIRST. `verify.fetch_text` is what criterion 3 uses and what
    # extract_citations cuts its quotes from, so matching against it is what makes this pass
    # agree with the gate instead of contradicting it.
    from src.cfp_monitor.verify import fetch_text                    # noqa: PLC0415
    pages: dict[str, list[str]] = {}
    flat_ok = 0
    for u in urls:
        text, _note = fetch_text(u)
        pages[u] = [text or ""]
        flat_ok += bool(text)
    print(f"  flat fetch read {flat_ok} of {len(urls)} page(s)")

    # Then the ladder, as a SECOND OPINION rather than a fallback: it is climbed for pages the
    # flat fetch could not read at all, and for pages whose quote did not match, because those
    # are exactly the two cases where one more rendering can still tell the truth.
    unmatched = {(r["deadline_evidence_url"] or "").strip() for r in rows
                 if not any(_norm(r["deadline_quote"]) in _norm(t)
                            for t in pages.get((r["deadline_evidence_url"] or "").strip(), []))}
    unmatched = sorted(u for u in unmatched if u in set(urls))
    if unmatched:
        print(f"  escalating {len(unmatched)} page(s) the flat fetch did not settle")
        from audit_evidence import escalate                          # noqa: PLC0415
        for u, (t, _via) in asyncio.run(escalate(unmatched)).items():
            pages.setdefault(u, []).append(t or "")

    out = verdicts(rows, pages)
    tally: dict[str, int] = {}
    for o in out:
        tally[o["CHECK"]] = tally.get(o["CHECK"], 0) + 1

    with open(a.output, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUT_COLUMNS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(out)

    print("\n=== verdicts ===")
    for state in ("verified", "no_quote", "unreadable"):
        print(f"  {state:<12}{tally.get(state, 0):>4}")
    print(f"\nwrote {a.output}")
    print("Feed it to: build_review_page.py --checks <file>")

    if a.apply:
        apply_verdicts(a.db, out)
    return 0


# `unreadable` is deliberately NOT written. It says we could not open the page - a statement
# about US, not about the date - and recording it as a verify_state would let a row we never
# managed to read count as a row we judged. It stays `unverified`, which is what it is, and
# the reason is kept in verify_detail so the next pass does not have to rediscover it.
VERDICT_TO_STATE = {"verified": "verified", "no_quote": "not_found"}


def apply_verdicts(db: str, out: list[dict]) -> None:
    """Persist the pass's findings. Keyed on upstream_event_id, per 5.4.

    Until 2026-09-14 nothing had ever written this column: every writer of `verify_state` in
    the repo targets `grounding_facts`, the conferences table. All 119 award rows therefore
    read `unverified`, which looked like a pass that had been skipped rather than one that
    did not exist.
    """
    con = sqlite3.connect(db)
    written: dict[str, int] = {}
    for o in out:
        state = VERDICT_TO_STATE.get(o["CHECK"], "unverified")
        detail = f"{o['CHECK']} {date.today().isoformat()} {o['CHECK_URL']}"[:500]
        n = con.execute(
            "UPDATE award_grounding_facts SET verify_state=?, verify_detail=?"
            " WHERE upstream_event_id=?", (state, detail, o["EVENT_ID"])).rowcount
        if n:
            written[state] = written.get(state, 0) + 1
    con.commit()
    remaining = con.execute(
        "SELECT COUNT(*) FROM award_grounding_facts WHERE verify_state='unverified'").fetchone()[0]
    con.close()
    print("\n=== written to award_grounding_facts ===")
    for state, n in sorted(written.items()):
        print(f"  {state:<12}{n:>4}")
    print(f"  still unverified (no cited page, or unreadable): {remaining}")


if __name__ == "__main__":
    sys.exit(main())
