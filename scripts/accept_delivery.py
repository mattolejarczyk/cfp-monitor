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
from urllib.parse import urlparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cfp_monitor.verify import fetch_text, link_status      # noqa: E402

# 36 since the v1.2 amendment added FORMAT as the last column (2026-08-05).
# Deliveries still emitting 35 columns predate the amendment and fail check 1,
# which is intended: upstream must adopt the column, not have it inferred for them.
# TWO SHAPES ARE VALID DURING THE v1.5 TRANSITION.
#   38  through v1.3 - FORMAT (v1.2), then LIFECYCLE_EVIDENCE_URL and LIFECYCLE_QUOTE (v1.3 R16)
#   43  v1.5 - appends ORGANIZER and the four SPONSOR_* columns
# Upstream agreed v1.5 on 2026-08-14 but gave no date for the first delivery carrying it, so
# both shapes have to pass until one arrives. Flipping straight to 43 would have rejected every
# delivery made between the agreement and their next run.
# ONE SHAPE AT A TIME once v1.5 lands: when a 43-column delivery has been accepted, drop 38.
ACCEPTED_COLS = {38, 43}
V15_COLS = ["ORGANIZER", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE"]
SPONSOR_VALUES = {"yes", "no", "unknown", ""}   # blank is read as Unknown (R18.1)
VALID_FORMATS = {"In-Person", "Virtual", "Hybrid"}
# Values that mean "not found" dressed up as data. 2.6 requires an honest blank.
PLACEHOLDERS = {"n/a", "na", "n.a.", "tbd", "tba", "unknown", "none", "null", "various",
                "multiple", "multiple cities", "multiple states", "multiple locations",
                "multiple regional cities", "varies", "to be announced",
                "to be determined", "-", "--"}
# A CITY that is not a city: the row is standing in for a series of events.
SERIES_HINT = re.compile(r"\bmultiple\b|\bvarious\b|\bregional\b|\bnationwide\b|\bseveral\b", re.I)
# Prose that says the event is over for good.
# A rotating event is not a dead one - EMO Hannover moves venue on a cycle.
ROTATION = re.compile(r'cycle dictates|rotat|alternat|moves to|held instead in', re.I)
DEFUNCT_PHRASES = re.compile(
    r"permanently ended|permanently concluded|no future editions|final edition|last edition|"
    r"discontinued|no longer (?:being )?(?:held|running)|has been cancell?ed|"
    r"ceased operations|will not (?:be held|return)|final year", re.I)
OPPORTUNITIES = {"Speaking", "Awards", "Exhibiting", "Registration"}
# Present-tense claims that assert a live call. Only legitimate with a citation behind them.
# "(?<!last )" keeps this off past-tense uses such as "the last active edition was held in
# July 2024", which describe a DORMANT event rather than asserting a live call.
ACTIVE_PROSE = re.compile(r"(?<!last )\b(active|now open|now accepting|currently accepting)\b", re.I)
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
        self.notes: list[tuple[str, str, list[str]]] = []
        self.rows: list[dict] = []
        self.raw_widths: list[tuple[int, int]] = []

    def add(self, num, name, failures):
        self.results.append((num, name, not failures, failures))

    def note(self, num, name, items):
        """Advisory: reported, but does not reject the delivery.

        For findings that are valid under the contract yet must not pass silently -
        a declared stub row is shippable under 2.1, but nobody should discover it
        in the customer's sheet.
        """
        self.notes.append((num, name, items))

    # ---- 1. structure ------------------------------------------------------
    def check_structure(self):
        with open(self.path, encoding="utf-8-sig", newline="") as fh:
            rdr = csv.reader(fh)
            header = next(rdr)
            bad = []
            width = len(header)
            for i, row in enumerate(rdr, start=2):
                if len(row) != width:
                    bad.append(f"line {i}: {len(row)} fields ({row[1][:40] if len(row) > 1 else '?'})")
        if width not in ACCEPTED_COLS:
            bad.insert(0, f"header has {width} columns, expected one of "
                          f"{sorted(ACCEPTED_COLS)} (38 = through v1.3, 43 = v1.5)")
        # A COUNT IS NOT A SCHEMA. 43 columns of the wrong names would sail through a length
        # check and every later check would then read shifted fields - the exact failure the
        # runbook warns about. Name them.
        elif width == 43 and [c.strip() for c in header[-5:]] != V15_COLS:
            bad.insert(0, f"43 columns but the last five are {[c.strip() for c in header[-5:]]}, "
                          f"expected {V15_COLS} (v1.5, appended in that order)")
        self.add("1", f"RFC 4180 - every row parses to the header's {width} fields", bad)
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
        # A row that states the event is DISCONTINUED is exempt: its prose legitimately
        # contains "active" in a past or negated sense - "the last active edition was
        # held in 2024", "no subsequent editions or active staging". Matching the bare
        # word there flags correct rows and invites someone to "fix" them. Rows claiming
        # a verified edition while saying they have ended are caught by check 2.1b.
        bad = [f'{self.g(r, "CONFERENCE")[:40]}: {self.g(r, "STATUS DETAILS")[:70]}'
               for r in self.rows
               if self.g(r, "IS_PROJECTED").lower() == "true"
               and ACTIVE_PROSE.search(self.g(r, "STATUS DETAILS"))
               and not DEFUNCT_PHRASES.search(self.g(r, "STATUS DETAILS"))]
        self.add("4", "No active-call prose on an IS_PROJECTED=true row (defunct rows exempt)", bad)

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
                # A ROLLING FORM has no closing date by definition, so a past date on
                # one is a priority or early-bird deadline, not a closure - BIO-Europe
                # 2026 states exactly that: "the priority review deadline was July 31,
                # but applications remain open on a rolling basis". Flagging those
                # invites someone to close a call that is genuinely still open.
                if self.g(r, "CFP MODEL TYPE").strip().lower() == "rolling form":
                    continue
                if self.g(r, "STATUS").lower() in ("open", "upcoming"):
                    bad.append(f'{self.g(r, "CONFERENCE")[:40]}: {d} but STATUS='
                               f'{self.g(r, "STATUS")}')
        self.add("6", f"No past deadline presented as open (as of {today}; rolling forms exempt)", bad)

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

        # ---- added 2026-08-06, folded in from a parallel validator ---------
        # Each of these came from a real defect seen in the Robotics or
        # Cybersecurity markets; none was covered by the checks above.

        # 2.6 - a placeholder is not a value. An honest blank is required instead.
        placeholders = []
        for r in self.rows:
            for c in ("CITY", "STATE_PROVINCE", "COUNTRY", "CONFERENCE DATES",
                      "SUBMISSION DEADLINE", "START DATE", "LOCATION"):
                if self.g(r, c).strip().lower() in PLACEHOLDERS:
                    placeholders.append(f'{self.g(r, "CONFERENCE")[:36]}: {c}={self.g(r, c)!r}')
        self.add("2.6", "No placeholder values where a real value belongs", placeholders)

        # 5.4 - a row standing in for many events cannot key on a city.
        # SecureWorld Expo produced CITY='Multiple Cities' across twelve events.
        series = [f'{self.g(r, "CONFERENCE")[:36]}: CITY={self.g(r, "CITY")!r}'
                  for r in self.rows
                  if SERIES_HINT.search(f'{self.g(r, "CITY")} {self.g(r, "STATE_PROVINCE")}')]
        self.add("5.4", "No row representing a SERIES rather than one event", series)

        # A call cannot close after the event it feeds has started. When it does,
        # the deadline belongs to a different edition or a different event.
        late = []
        for r in self.rows:
            d, s = self.g(r, "SUBMISSION DEADLINE"), self.g(r, "START DATE")
            if (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)
                    and d > s):
                late.append(f'{self.g(r, "CONFERENCE")[:36]}: deadline {d} after start {s}')
        self.add("6b", "Submission deadline precedes the event it feeds", late)

        # A row whose own prose says the event has ended cannot claim a verified
        # edition. ShmooCon and Japan Robot Week both did.
        defunct = []
        for r in self.rows:
            prose = f'{self.g(r, "STATUS DETAILS")} {self.g(r, "NOTES")} {self.g(r, "DEADLINE_QUOTE")}'
            if not DEFUNCT_PHRASES.search(prose):
                continue
            if (self.g(r, "IS_PROJECTED").lower() == "false"
                    or "verified" in self.g(r, "GROUNDING_CONFIDENCE").lower()):
                defunct.append(f'{self.g(r, "CONFERENCE")[:36]}: says ended, claims '
                               f'{self.g(r, "GROUNDING_CONFIDENCE")!r}')
        self.add("2.1b", "No discontinued event claiming a verified edition", defunct)

        # EDITION is a year. DEF CON 34 arrived with EDITION='34', which then
        # keyed its EVENT_ID as '34-def-con-34-...'.
        bad_edition = [f'{self.g(r, "CONFERENCE")[:36]}: EDITION={self.g(r, "EDITION")!r}'
                       for r in self.rows
                       if self.g(r, "EDITION")
                       and not re.fullmatch(r"(19|20)\d{2}", self.g(r, "EDITION").strip())]
        self.add("R8d", "EDITION is a plain 4-digit year", bad_edition)

        # FORMAT (v1.2). Blank is allowed - an honest blank beats a guessed format.
        bad_format = [f'{self.g(r, "CONFERENCE")[:36]}: FORMAT={self.g(r, "FORMAT")!r}'
                      for r in self.rows
                      if self.g(r, "FORMAT") and self.g(r, "FORMAT") not in VALID_FORMATS]
        self.add("R12", "FORMAT is In-Person, Virtual, Hybrid or blank", bad_format)

        # R3b - a citation must be the page carrying the sentence, not the site's front door.
        #
        # Measured 2026-08-10: DEADLINE_EVIDENCE_URL was identical to MAIN_INFO_URL on 42% of
        # cited rows. Those are placeholders - the field filled to be non-empty rather than to
        # record where a deadline was read. CFP deadlines are rarely on a homepage, so such a
        # citation can never confirm anything: we fetch it, the sentence is not there, and a
        # CORRECT deadline is labelled unverified forever.
        #
        # This is in the GATE rather than left to the prompt on purpose. The same ask was
        # already sent as a prompt rule for submission URLs ("never output a URL you have not
        # retrieved") and 45 unreachable links arrived anyway. A request is not a control.
        #
        # Only fires when a deadline is actually CLAIMED - a blank deadline needs no citation,
        # and an honest blank is always acceptable (2.6).
        placeholder_cite = []
        for r in self.rows:
            if not self.g(r, "SUBMISSION DEADLINE"):
                continue
            ev, main = self.g(r, "DEADLINE_EVIDENCE_URL"), self.g(r, "MAIN_INFO_URL")
            if not ev:
                continue
            if ev.rstrip("/").lower() == main.rstrip("/").lower():
                placeholder_cite.append(
                    f'{self.g(r, "CONFERENCE")[:38]}: evidence URL is the main URL - {ev[:52]}')
            elif urlparse(ev).path.rstrip("/") in ("", "/"):
                placeholder_cite.append(
                    f'{self.g(r, "CONFERENCE")[:38]}: evidence URL is a bare homepage - {ev[:52]}')
        # ADVISORY, not a rejection - deliberately. The acceptance gate is a TWO-SIDED
        # instrument (section 8 divides its criteria between upstream's and ours), so adding a
        # criterion that fails every delivery would judge their work against a standard they
        # have never agreed to. Same reason the 35-vs-38 column gap is flagged here rather than
        # patched into the contract unilaterally.
        #
        # Promote to self.add() - a hard FAIL - once amendment v1.4 is agreed. Until then this
        # reports on every run so nobody can claim they were not told.
        self.note("R3b", "Claimed deadline cites the homepage, not the page carrying it "
                         "(advisory pending amendment v1.4)", placeholder_cite)

        # An ungrounded stub is shippable but must be declared, never silent.
        # R16 - a lifecycle claim is the most consequential finding the research
        # produces: it removes an event from the pipeline for good. It must carry its
        # OWN citation, in its OWN fields, so an R1 deadline withdrawal can never
        # delete it. Prose alone is not enough (R16.5).
        unevidenced = []
        for r in self.rows:
            prose = f'{self.g(r, "STATUS DETAILS")} {self.g(r, "NOTES")}'
            if not DEFUNCT_PHRASES.search(prose) or ROTATION.search(prose):
                continue
            if not (self.g(r, "LIFECYCLE_EVIDENCE_URL") and self.g(r, "LIFECYCLE_QUOTE")):
                unevidenced.append(f'{self.g(r, "CONFERENCE")[:40]}: says the event has ended, '
                                   f'but carries no lifecycle citation')
        self.add("R16", "A discontinuation claim carries its own evidence", unevidenced)

        # ---- R18, v1.5. Skipped entirely on a pre-v1.5 delivery. ----
        # A cost figure is the most consequential number in this file: it either kills an
        # opportunity or commits real budget. It gets the same standard as a deadline.
        if "SPONSOR_REQUIRED" in (self.rows[0].keys() if self.rows else ()):
            bad_val, unevidenced_cost = [], []
            for r in self.rows:
                req = self.g(r, "SPONSOR_REQUIRED")
                if req.lower() not in SPONSOR_VALUES:
                    bad_val.append(f'{self.g(r, "CONFERENCE")[:40]}: SPONSOR_REQUIRED={req!r}')
                # R18.3 - "Yes" is a claim that costs the customer a decision. Evidence it.
                # ONLY SPONSOR_URL IS REQUIRED OF UPSTREAM. SPONSOR_QUOTE is ours to extract
                # from that page (R20a), exactly as with DEADLINE_QUOTE, so demanding it here
                # would reject a delivery for a field we told them to leave blank.
                if req.lower() == "yes" and not self.g(r, "SPONSOR_URL"):
                    unevidenced_cost.append(f'{self.g(r, "CONFERENCE")[:40]}: sponsorship '
                                            f'required, but no SPONSOR_URL to read it on')
                # A cost with no stated requirement is incoherent - which is it?
                if self.g(r, "SPONSOR_COST") and req.lower() in ("no", ""):
                    bad_val.append(f'{self.g(r, "CONFERENCE")[:40]}: has a SPONSOR_COST but '
                                   f'SPONSOR_REQUIRED={req or "(blank)"!r}')
            self.add("R18a", "SPONSOR_REQUIRED is Yes, No, Unknown or blank", bad_val)
            self.add("R18b", "A sponsorship requirement carries its own evidence",
                     unevidenced_cost)

        stubs = [self.g(r, "CONFERENCE")[:40] for r in self.rows
                 if "Audit Exception" in self.g(r, "STATUS DETAILS")]
        if stubs:
            self.note("STUB", f"{len(stubs)} ungrounded stub row(s) - valid under 2.1 but "
                              f"they must be declared in the manifest", stubs)

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
        for num, name, items in self.notes:
            print(f"  [NOTE] {num:<4} {name}  ({len(items)})")
            for i in items[:verbose_limit]:
                print(f"           - {i}")
            if len(items) > verbose_limit:
                print(f"           ... and {len(items) - verbose_limit} more")
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
