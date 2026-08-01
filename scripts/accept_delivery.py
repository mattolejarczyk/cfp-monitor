"""Run the acceptance gate from docs/operations/pipeline-contract.md against a delivery.

    python scripts/accept_delivery.py <market.csv> [--no-network] [--json out.json]

Checks the criteria that are decidable from the file itself (contract 1-5, plus the schema
rules in R8/R11). Criteria 7 and 8 need the database and are covered by the import/verify
pass, not here.

Exit code 0 when every check passes, 1 otherwise -- so this can gate a pipeline step.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.verify import fetch_text, link_status      # noqa: E402

EXPECTED_COLS = 35
OPPORTUNITIES = {"Speaking", "Awards", "Exhibiting", "Registration"}
# Present-tense claims that assert a live call. Only legitimate with a citation behind them.
ACTIVE_PROSE = re.compile(r"\b(active|now open|now accepting|currently accepting)\b", re.I)
# Words that only appear in a venue name. "Park" is deliberately absent: Menlo Park and
# Overland Park are cities, and flagging them would train people to ignore this check.
VENUE_HINT = re.compile(
    r"\b(messe|expo|centre|convention|fira|pavilion|arena|showplace|"
    r"koelnmesse|terminal|ahoy|sniec|lvcc|iicc|nec)\b", re.I)


def norm(text: str) -> str:
    """Normalize for quote comparison: entities, quotes, dashes, whitespace, case."""
    t = (text or "")
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&#8217;", "'"), ("&rsquo;", "'"),
                 ("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("−", "-")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().lower()


class Gate:
    def __init__(self, path: str, network: bool = True):
        self.path, self.network = Path(path), network
        self.results: list[tuple[str, str, bool, list[str]]] = []
        self.rows: list[dict] = []
        self.raw_widths: list[tuple[int, int]] = []

    def add(self, num, name, failures):
        self.results.append((num, name, not failures, failures))

    # ---- 1. structure ------------------------------------------------------
    def check_structure(self):
        with open(self.path, encoding="utf-8-sig", newline="") as fh:
            rdr = csv.reader(fh)
            header = next(rdr)
            bad = []
            for i, row in enumerate(rdr, start=2):
                if len(row) != EXPECTED_COLS:
                    bad.append(f"line {i}: {len(row)} fields ({row[1][:40] if len(row) > 1 else '?'})")
        if len(header) != EXPECTED_COLS:
            bad.insert(0, f"header has {len(header)} columns, expected {EXPECTED_COLS}")
        self.add("1", f"RFC 4180 - every row parses to {EXPECTED_COLS} fields", bad)
        with open(self.path, encoding="utf-8-sig", newline="") as fh:
            self.rows = list(csv.DictReader(fh))

    def g(self, r, k):
        return (r.get(k) or "").strip()

    # ---- 2 & 3. citations --------------------------------------------------
    def check_citations(self):
        if not self.network:
            self.add("2", "Cited pages resolve (no 404s)", ["SKIPPED - --no-network"])
            self.add("3", "Cited page contains its quote", ["SKIPPED - --no-network"])
            return
        cache: dict[str, tuple] = {}
        dead, missing_quote = [], []
        for r in self.rows:
            url = self.g(r, "DEADLINE_EVIDENCE_URL")
            if not url:
                continue
            if url not in cache:
                code, _ = link_status(url)
                text, _ = fetch_text(url)
                cache[url] = (code, text)
            code, text = cache[url]
            name = self.g(r, "CONFERENCE")[:40]
            if code in (404, 410):
                dead.append(f"{name}: HTTP {code} {url}")
                continue
            if code == 403:
                continue                       # blocked-but-trusted; exempt from the quote test
            quote = self.g(r, "DEADLINE_QUOTE")
            if quote and text and norm(quote) not in norm(text):
                # Distinguish a PARAPHRASE from an unsupported claim. If the deadline itself
                # is on the page, the substance was read correctly and only the wording was
                # rewritten -- a much smaller fault than a citation that supports nothing,
                # and one that needs a different fix.
                from src.cfp_monitor.verify import _parse_date, find_date
                d = _parse_date(self.g(r, "SUBMISSION DEADLINE"))
                kind = "paraphrase, date IS on page" if (d and find_date(text, d)) \
                    else "quote and date both absent"
                missing_quote.append(f'{name}: {kind} - "{quote[:52]}"')
        self.add("2", "Cited pages resolve (404/410 = fail, 403 allowed)", dead)
        self.add("3", "Cited page contains its quote verbatim (403 exempt)", missing_quote)

    # ---- 4. prose vs projection -------------------------------------------
    def check_prose(self):
        bad = [f'{self.g(r, "CONFERENCE")[:40]}: {self.g(r, "STATUS DETAILS")[:70]}'
               for r in self.rows
               if self.g(r, "IS_PROJECTED").lower() == "true"
               and ACTIVE_PROSE.search(self.g(r, "STATUS DETAILS"))]
        self.add("4", "No active-call prose on an IS_PROJECTED=true row", bad)

    # ---- 5. opportunity isolation -----------------------------------------
    def check_opportunity(self):
        bad = [f'{self.g(r, "CONFERENCE")[:40]}: {self.g(r, "OPPORTUNITY_TYPE")} '
               f'carries deadline {self.g(r, "SUBMISSION DEADLINE")}'
               for r in self.rows
               if self.g(r, "OPPORTUNITY_TYPE") in ("Exhibiting", "Registration")
               and self.g(r, "SUBMISSION DEADLINE")]
        self.add("5", "No Exhibiting/Registration row carrying a deadline", bad)
        bad_enum = [f'{self.g(r, "CONFERENCE")[:40]}: {self.g(r, "OPPORTUNITY_TYPE")!r}'
                    for r in self.rows
                    if self.g(r, "OPPORTUNITY_TYPE") not in OPPORTUNITIES]
        self.add("5b", "OPPORTUNITY_TYPE is one of the four enum values", bad_enum)

    # ---- 6. past deadline shown open --------------------------------------
    def check_past(self, today: date):
        bad = []
        for r in self.rows:
            d = self.g(r, "SUBMISSION DEADLINE")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d < today.isoformat():
                if self.g(r, "STATUS").lower() in ("open", "upcoming"):
                    bad.append(f'{self.g(r, "CONFERENCE")[:40]}: {d} but STATUS='
                               f'{self.g(r, "STATUS")}')
        self.add("6", f"No past deadline presented as open (as of {today})", bad)

    # ---- R8 / R11 schema rules --------------------------------------------
    def check_schema_rules(self):
        derived = [self.g(r, "CONFERENCE")[:40] for r in self.rows
                   if self.g(r, "GATED_STATUS") or self.g(r, "ISSUES")]
        self.add("R8a", "GATED_STATUS and ISSUES left blank upstream", derived)

        venues = [f'{self.g(r, "CONFERENCE")[:36]}: CITY={self.g(r, "CITY")!r}'
                  for r in self.rows if VENUE_HINT.search(self.g(r, "CITY"))]
        self.add("R8b", "CITY holds a city, not a venue", venues)

        seen, dupes = set(), []
        for r in self.rows:
            eid = self.g(r, "EVENT_ID")
            if eid in seen:
                dupes.append(eid)
            seen.add(eid)
        self.add("R8c", "EVENT_ID unique per row", dupes)

        bad_bind = []
        for r in self.rows:
            gc, proj = self.g(r, "GROUNDING_CONFIDENCE"), self.g(r, "IS_PROJECTED").lower()
            if not gc or proj not in ("true", "false"):
                continue
            word = gc.split("(")[0].strip().lower()
            if proj == "true" and word != "projected":
                bad_bind.append(f'{self.g(r, "CONFERENCE")[:36]}: {gc!r} but IS_PROJECTED=true')
            if proj == "false" and word != "verified":
                bad_bind.append(f'{self.g(r, "CONFERENCE")[:36]}: {gc!r} but IS_PROJECTED=false')
        self.add("R11", "GROUNDING_CONFIDENCE bound to IS_PROJECTED", bad_bind)

        # R2: a future deadline claimed as verified must carry a citation.
        bad_proj = []
        today = date.today().isoformat()
        for r in self.rows:
            d = self.g(r, "SUBMISSION DEADLINE")
            if (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and d >= today
                    and self.g(r, "IS_PROJECTED").lower() == "false"
                    and not self.g(r, "DEADLINE_EVIDENCE_URL")):
                bad_proj.append(f'{self.g(r, "CONFERENCE")[:36]}: {d} verified with no citation')
        self.add("R2", "Future date marked verified only with a citation", bad_proj)

    # ---- 7 & 8. downstream criteria, once the delivery is loaded ----------
    def check_loaded(self, db: str, market: str):
        """Contract criteria 7 and 8, which need the database rather than the file."""
        from src.cfp_monitor.storage import Store
        from src.cfp_monitor.customer_format import to_customer_row

        store = Store(db)
        keys = {r[0] for r in store.db.execute(
            "SELECT conference_key FROM conference_markets WHERE market=?", (market,))}
        recs = [r for r in store.export_dicts() if r["key"] in keys]
        if not recs:
            self.add("7", "Rows carry only their own evidence", [f"no rows for market {market!r}"])
            return

        # 7. Test the claim pick_claim ACTUALLY attached, not an arbitrary one sharing the key.
        # Comparing against "whichever row the DB returns first" is the very bug pick_claim
        # exists to fix, and would report a failure on rows that are correct.
        from collections import defaultdict

        from src.cfp_monitor.storage import choose_claim
        claims = defaultdict(list)
        for row in store.db.execute(
                "SELECT conference_key, verify_state, name, edition FROM grounding_facts"):
            claims[row[0]].append({"verify_state": row[1], "_name": row[2], "_edition": row[3]})
        borrowed = []
        for r in recs:
            chosen = choose_claim(dict(r), claims.get(r["key"], []))
            if chosen is None:
                continue
            ours = str(r.get("edition") or "")[:4]
            theirs = str(chosen.get("_edition") or "")[:4]
            if ours.isdigit() and theirs.isdigit() and ours != theirs:
                borrowed.append(f'{(r.get("name") or "")[:40]}: record {ours} '
                                f'wearing claim {theirs} ({chosen["_name"][:30]})')
        self.add("7", "No row wearing another event's evidence", borrowed)

        # 8. every open row must carry a usable label.
        blank = []
        for r in recs:
            row = to_customer_row(r)
            if row["RESEARCH STATUS"].startswith(("Open", "Upcoming")) and not row["CONFIDENCE"]:
                blank.append(f'{row["CONFERENCE"][:40]}: {row["RESEARCH STATUS"]} but CONFIDENCE blank')
        self.add("8", "Open rows are labelled Confirmed or Unconfirmed", blank)
        store.close()

    def run(self, today: date, db: str = "", market: str = ""):
        self.check_structure()
        if not self.rows:
            return
        self.check_citations()
        self.check_prose()
        self.check_opportunity()
        self.check_past(today)
        self.check_schema_rules()
        if db and market:
            self.check_loaded(db, market)

    def report(self, verbose_limit: int = 12) -> bool:
        print(f"\n{'=' * 74}\nACCEPTANCE GATE - {self.path.name}  ({len(self.rows)} rows)\n{'=' * 74}")
        ok = True
        for num, name, passed, failures in self.results:
            skipped = failures and failures[0].startswith("SKIPPED")
            mark = "PASS" if passed else ("SKIP" if skipped else "FAIL")
            if not passed and not skipped:
                ok = False
            print(f"  [{mark}] {num:<4} {name}"
                  + ("" if passed or skipped else f"  ({len(failures)})"))
            if not passed and not skipped:
                for f in failures[:verbose_limit]:
                    print(f"           - {f}")
                if len(failures) > verbose_limit:
                    print(f"           ... and {len(failures) - verbose_limit} more")
        print(f"\n  RESULT: {'ACCEPTED' if ok else 'REJECTED'}\n")
        return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the delivery acceptance gate.")
    ap.add_argument("csv_paths", nargs="+")
    ap.add_argument("--no-network", action="store_true", help="skip the citation fetches")
    ap.add_argument("--json", help="write machine-readable results here")
    ap.add_argument("--db", help="database to check criteria 7-8 against (needs --market)")
    ap.add_argument("--market", help="canonical market name, e.g. \"Consumer Electronics\"")
    a = ap.parse_args()

    today = date.today()
    all_ok, payload = True, {}
    for p in a.csv_paths:
        gate = Gate(p, network=not a.no_network)
        gate.run(today, db=a.db or "", market=a.market or "")
        all_ok &= gate.report()
        payload[Path(p).name] = [
            {"check": n, "name": nm, "passed": ok, "failures": f}
            for n, nm, ok, f in gate.results]
    if a.json:
        Path(a.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {a.json}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
