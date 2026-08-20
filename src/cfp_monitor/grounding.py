"""Import + normalize a Google-Search-grounding master list (the v4 schema).

Grounding is our DISCOVERY layer: broad, fast, and forward-looking, but its specifics are
unverified (projected deadlines, occasionally fabricated deep-links). Our crawler is the
VERIFICATION layer. The contract between them is deliberate:

    verified      page confirms the fact            -> promote
    contradicted  page states something different   -> we override grounding
    not_found     page unreachable / fact absent    -> GROUNDING STANDS, flagged unverified
    self_contra   the row disproves itself (dates)  -> flag + gate at display; source preserved

"Not found" is not a disproof. That is why nothing here ever deletes or rewrites a grounding
value: raw fields are preserved verbatim and every correction is an ADDITIONAL derived field.

What this module fixes deterministically (things an LLM should not be trusted with):
  * CITY holding a VENUE ("Messe Berlin" -> "Berlin"), using the STATE/COUNTRY columns.
  * The canonical EVENT_ID, recomputed from clean parts. Never trust a model-generated join
    key -- one inconsistency silently splits or merges records.
  * The CFP-model vocabulary, collapsed to a controlled enum.
  * Duplicate rows.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

# ---------------------------------------------------------------- vocabulary --
# Controlled enum for how a call operates. Everything maps into exactly one of these.
CFP_MODELS = ("Fixed Deadline", "Rolling Form", "Invite Only", "Not Announced")
_MODEL_ALIASES = {
    "fixeddeadline": "Fixed Deadline",
    "rollingform": "Rolling Form",
    "rolling": "Rolling Form",
    "inviteonly": "Invite Only",
    "invitationonly": "Invite Only",
    "curatedinvite": "Invite Only",
    "invitecurated": "Invite Only",
    "curated": "Invite Only",
    "notannounced": "Not Announced",
    "tbd": "Not Announced",
}

# Tokens that mark a LOCATION fragment as a VENUE rather than a settlement.
_VENUE_HINT = re.compile(
    r"\b(centre|center|messe|fira|expo|exhibition|convention|congress|hall|arena|stadium|"
    r"hotel|resort|palace|pavilion|campus|university|institute|college|park|"
    r"nangang|asiaworld|station)\b", re.I)
_ONLINE_HINT = re.compile(r"\b(online|virtual|remote)\b", re.I)
_TBD_HINT = re.compile(r"\b(tbd|tba|to be (announced|determined)|unknown)\b", re.I)


def normalize_cfp_model(value: Optional[str]) -> str:
    """Collapse a free-text model label onto the controlled enum. Unknown -> Not Announced."""
    key = re.sub(r"[^a-z]", "", (value or "").lower())
    return _MODEL_ALIASES.get(key, "Not Announced")


# ------------------------------------------------------------------ location --
def clean_city(location: str, city: str = "", state: str = "", country: str = "") -> str:
    """Best-effort real settlement name for a row.

    Grounding frequently put the VENUE in CITY because it took the first comma-token of
    "Messe Berlin, Berlin, Germany". We instead drop the country/state tokens and take the
    last remaining fragment that does not look like a venue -- which is the city in the
    conventional "Venue, City, [State,] Country" ordering. Falls back to the supplied CITY
    when nothing better can be established (never invents a place).
    """
    if _TBD_HINT.search(city or "") or _TBD_HINT.search(location or ""):
        if not (city and not _TBD_HINT.search(city)):
            return ""
    # TRUST A DELIVERED CITY THAT DOES NOT LOOK LIKE A VENUE.  (added 2026-08-08)
    #
    # This function exists because grounding used to put the VENUE in CITY. Upstream fixed
    # that; CITY is now reliable, and overriding it with a LOCATION parse made things worse
    # on 23 of 26 rows in the 8-market delivery. Two ways it failed:
    #
    #   Seattle -> Washington   STATE_PROVINCE/COUNTRY are often blank, so there is nothing
    #   Buffalo -> New York     to drop and "last fragment wins" lands on the state.
    #   Rotterdam -> Netherlands
    #
    #   Tokyo -> Tokyo Big Sight   when CITY == STATE_PROVINCE (city-states and prefectures)
    #   Berlin -> Hilton Berlin    pass 1 drops the state, which IS the city, leaving the
    #   Singapore -> Marina Bay Sands   venue - and being truthy it short-circuits pass 2.
    #
    # Parsing LOCATION stays as the FALLBACK for when CITY is missing or is itself a venue.
    # Contract 2.5: decline rather than guess. A delivered city we cannot fault beats a
    # heuristic that silently substitutes a state, a country or a hotel.
    if city and not _VENUE_HINT.search(city):
        return city
    parts = [p.strip() for p in re.split(r"[,/]", location or "") if p.strip()]
    countries = {(country or "").strip().lower(), "usa", "us", "united states",
                 "uk", "united kingdom"}

    def pick(drop: set[str]) -> str:
        cand = [p for p in parts if p.lower() not in drop and not _TBD_HINT.search(p)]
        for c in reversed(cand):                     # last non-venue fragment wins
            if not _VENUE_HINT.search(c):
                return re.sub(r"\s*\(.*?\)\s*", " ", c).strip(" -")
        return ""

    st = (state or "").strip().lower()
    co = (country or "").strip().lower()
    # Pass 1 drops the state so "Las Vegas, Nevada, USA" -> "Las Vegas".
    # Pass 2 keeps the state, because in a CITY-STATE the state IS the city ("Messe Berlin,
    # Berlin, Germany" has STATE_PROVINCE="Berlin"); dropping it would leave only the venue.
    result = pick(countries | {st}) or pick(countries)
    # Pass 3 keeps the COUNTRY too, but only for a true city-state -- signalled by
    # country == state ("AsiaWorld-Expo, Hong Kong"). Restricting it to that case stops a
    # plain country name from ever being promoted into the city field.
    if not result and st and st == co:
        result = pick(set())
    if result:
        return result
    # Everything looked like a venue: keep the supplied city only if it isn't a venue too.
    if city and not _VENUE_HINT.search(city):
        return city
    return ""


def slug(text: str, max_len: int = 48, strip_years: bool = False) -> str:
    """Lowercase hyphen slug, trimmed at a word boundary so IDs stay readable."""
    s = re.sub(r"\s*\(.*?\)\s*", " ", text or "")          # drop parenthetical asides
    if strip_years:
        s = re.sub(r"(?<!\d)(19|20)\d{2}(?!\d)", " ", s)   # year is a separate ID part
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if len(s) <= max_len:
        return s
    cut = s[:max_len]
    return cut.rsplit("-", 1)[0] if "-" in cut else cut


def event_id(name: str, edition: str, city: str, location: str = "",
             opportunity: str = "") -> str:
    """Canonical key: <year>-<name-slug>-<city|virtual|tbd>[-<opportunity>].

    Market is deliberately EXCLUDED: one event can serve several markets (CES is Consumer
    Electronics AND Semiconductor), and market-in-the-key would split it into two records.
    Membership belongs in the many-to-many table instead.

    OPPORTUNITY is included, because one event genuinely runs several calls with different
    deadlines -- CEDIA Expo has a call for presentations AND a Best of Show awards entry. Those
    are separate opportunities and the client acts on them separately, so they need separate
    rows. Without this they collapse onto one key and the second silently overwrites the first.

    Speaking stays UNSUFFIXED: it is the default opportunity and every record imported before
    this column existed is one, so leaving it bare keeps those keys stable instead of orphaning
    several hundred rows across the markets already loaded.
    """
    year = (edition or "").strip()[:4]
    year = year if year.isdigit() else "tbd"
    place = slug(city, 28)
    if not place:
        place = "virtual" if _ONLINE_HINT.search(location or "") else "tbd"
    base = f"{year}-{slug(name, strip_years=True)}-{place}".strip("-")
    opp = slug(opportunity, 14)
    return base if opp in ("", "speaking") else f"{base}-{opp}"


# --------------------------------------------------------------------- dates --
def parse_loose_date(value: Optional[str]) -> Optional[date]:
    """m/d/yyyy or yyyy-mm-dd only. Anything vaguer returns None -- never guessed."""
    s = (value or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        try:
            return date(int(m[3]), int(m[1]), int(m[2]))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------- model --
@dataclass
class GroundingRow:
    """One normalized seed record. `raw` keeps the source row verbatim for audit."""
    event_id: str
    name: str
    url: str
    market: str
    edition: str
    city: str
    state: str
    country: str
    deadline: str
    submission_url: str
    cfp_model: str
    grounding_status: str                 # RAW status as grounding reported it
    overview: str
    categories: str
    coordinator_email: str
    deadline_quote: str
    is_projected: str
    source_as_of: str
    deadline_evidence_url: str
    main_info_url: str
    # v1.5 - defaulted so a pre-v1.5 (38-column) delivery still constructs cleanly.
    organizer: str = ""
    sponsor_required: str = "Unknown"
    sponsor_url: str = ""
    sponsor_cost: str = ""
    sponsor_quote: str = ""
    issues: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def deadline_date(self) -> Optional[date]:
        return parse_loose_date(self.deadline)


def _placeholder(value: Optional[str]) -> str:
    """Grounding backfilled the new provenance fields with 'x'. Treat that as empty."""
    v = (value or "").strip()
    return "" if v.lower() in ("x", "n/a", "na", "-", "none") else v


def detect_issues(row: GroundingRow, today: Optional[date] = None) -> list[str]:
    """Deterministic, crawl-free contradictions. These are self-disproving: the row's own
    fields are inconsistent, so no page fetch is needed to know something is wrong."""
    today = today or date.today()
    out: list[str] = []
    dl = row.deadline_date
    status = (row.grounding_status or "").strip().lower()
    if dl and dl < today and status in ("open", "upcoming"):
        out.append(f"PASSED_DEADLINE ({(today - dl).days} days past)")
    if dl and dl >= today and status == "closed":
        out.append("CLOSED_BUT_DEADLINE_FUTURE")
    start = parse_loose_date(row.raw.get("START DATE"))
    if dl and start and dl > start:
        out.append("DEADLINE_AFTER_EVENT_START")
    if row.cfp_model == "Fixed Deadline" and not row.deadline:
        out.append("FIXED_MODEL_NO_DEADLINE")
    if not row.city:
        out.append("NO_CITY")
    if not (row.submission_url or "").startswith("http"):
        out.append("NO_SUBMISSION_URL")
    return out


def gated_status(row: GroundingRow, today: Optional[date] = None) -> str:
    """Display status after the past-date gate. DERIVED, never stored over the raw value:
    a past-dated call cannot be open, and the row self-corrects as dates pass."""
    today = today or date.today()
    dl = row.deadline_date
    status = (row.grounding_status or "").strip() or "Unknown"
    if dl and dl < today and status.lower() in ("open", "upcoming"):
        return "Closed"
    return status


# -------------------------------------------------------------------- loader --
_COL = {
    "name": "CONFERENCE", "url": "CONFERENCE URL", "market": "Market", "edition": "EDITION",
    "city": "CITY", "state": "STATE_PROVINCE", "country": "COUNTRY", "location": "LOCATION",
    "deadline": "SUBMISSION DEADLINE", "submission_url": "SUBMISSION URL",
    "cfp_model": "CFP MODEL TYPE", "status": "STATUS", "overview": "OVERVIEW",
    "categories": "CATEGORIES", "email": "COORDINATOR EMAIL",
    "quote": "DEADLINE_QUOTE", "projected": "IS_PROJECTED", "as_of": "SOURCE_AS_OF",
    "dl_evidence": "DEADLINE_EVIDENCE_URL", "main_info": "MAIN_INFO_URL",
    "opportunity": "OPPORTUNITY_TYPE",
    # v1.5. Upstream populates the first four; SPONSOR_QUOTE is ours (R20a) and arrives
    # blank, so it is read but never allowed to overwrite a quote we extracted.
    "organizer": "ORGANIZER", "sponsor_required": "SPONSOR_REQUIRED",
    "sponsor_url": "SPONSOR_URL", "sponsor_cost": "SPONSOR_COST",
    "sponsor_quote": "SPONSOR_QUOTE",
}


def normalize_rows(raw_rows: Iterable[dict], today: Optional[date] = None
                   ) -> tuple[list[GroundingRow], dict]:
    """Normalize + dedupe grounding rows, returning (rows, report).

    Dedupe is on (event_id, market): the SAME event legitimately appears once per market it
    serves, so only an exact event+market repeat is a true duplicate.
    """
    today = today or date.today()
    rows: list[GroundingRow] = []
    seen: set[tuple[str, str]] = set()
    report = {"input": 0, "kept": 0, "duplicates": 0, "city_repaired": 0,
              "model_normalized": 0, "issue_counts": {}}

    for raw in raw_rows:
        report["input"] += 1

        def v(key: str) -> str:
            return (raw.get(_COL[key]) or "").strip()

        city_in, location = v("city"), v("location")
        city = clean_city(location, city_in, v("state"), v("country"))
        if city and city != city_in:
            report["city_repaired"] += 1

        model_in = v("cfp_model")
        model = normalize_cfp_model(model_in)
        if model_in and model != model_in:
            report["model_normalized"] += 1

        row = GroundingRow(
            event_id=event_id(v("name"), v("edition"), city, location, v("opportunity")),
            name=v("name"), url=v("url"), market=v("market"), edition=v("edition"),
            city=city, state=v("state"), country=v("country"),
            deadline=v("deadline"), submission_url=v("submission_url"),
            cfp_model=model, grounding_status=v("status"), overview=v("overview"),
            categories=v("categories"), coordinator_email=v("email"),
            deadline_quote=_placeholder(v("quote")),
            is_projected=_placeholder(v("projected")),
            source_as_of=_placeholder(v("as_of")),
            deadline_evidence_url=v("dl_evidence"), main_info_url=v("main_info"),
            organizer=v("organizer"),
            sponsor_required=v("sponsor_required") or "Unknown",
            sponsor_url=v("sponsor_url"),
            sponsor_cost=v("sponsor_cost"),
            sponsor_quote=v("sponsor_quote"),
            raw=dict(raw),
        )
        key = (row.event_id, row.market.lower())
        if key in seen:
            report["duplicates"] += 1
            continue
        seen.add(key)
        row.issues = detect_issues(row, today)
        for i in row.issues:
            label = i.split(" (")[0]
            report["issue_counts"][label] = report["issue_counts"].get(label, 0) + 1
        rows.append(row)

    # An id that covers more than one distinct SOURCE URL means the slug merged what are
    # probably different events (e.g. a co-located sub-track). Never silently accept that --
    # flag it for a human, the same discipline we apply to every other ambiguity.
    urls_per_id: dict[str, set[str]] = {}
    for r in rows:
        urls_per_id.setdefault(r.event_id, set()).add(r.url.lower().rstrip("/"))
    for r in rows:
        if len(urls_per_id.get(r.event_id, ())) > 1:
            r.issues.append("ID_COVERS_MULTIPLE_URLS")
            report["issue_counts"]["ID_COVERS_MULTIPLE_URLS"] =                 report["issue_counts"].get("ID_COVERS_MULTIPLE_URLS", 0) + 1

    report["kept"] = len(rows)
    report["distinct_events"] = len({r.event_id for r in rows})
    report["markets"] = sorted({r.market for r in rows if r.market})
    return rows, report


def load_master_csv(path: str, today: Optional[date] = None) -> tuple[list[GroundingRow], dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return normalize_rows(list(csv.DictReader(fh)), today)


# ---------------------------------------------------------------------- seed --
def seed_store(store, rows: Iterable[GroundingRow]) -> dict:
    """Write normalized grounding rows into the DISCOVERY table and record market membership.

    Deliberately does NOT touch the `conferences` table's crawl-produced fields. Grounding is
    an unverified third-party claim; our verified record must stay authoritative. What this
    does do:
      * upsert the claim into `grounding_facts` (raw values preserved),
      * stamp `event_id` onto an existing verified record so the two layers can be joined,
      * add market membership, which is INPUT metadata and safe to assert either way.
    A conference grounding knows about but we have never crawled is left for the verification
    pass to pick up -- we do not fabricate a `conferences` row from unverified data.
    """
    from .markets import MarketRegistry
    from .storage import normalize_key

    now = _now_iso()
    stats = {"inserted": 0, "updated": 0, "matched_existing": 0, "new_to_us": 0,
             "markets_added": 0, "unmapped_markets": {}}
    existing = {r["key"] for r in store.all_records()}
    # Grounding uses its own market spellings ("AdditiveMfg"). Route every one through the
    # controlled registry so the vocabulary cannot fork; anything it cannot resolve is
    # REPORTED rather than silently registered as a new market.
    registry = MarketRegistry(store.db)

    for row in rows:
        key = normalize_key(row.url)
        known = key in existing
        stats["matched_existing" if known else "new_to_us"] += 1
        was = store.db.execute("SELECT 1 FROM grounding_facts WHERE event_id=?",
                               (row.event_id,)).fetchone()
        store.db.execute(
            "INSERT INTO grounding_facts (event_id, conference_key, name, url, city,"
            " state_province, country, edition, deadline, submission_url, cfp_model, status,"
            " overview, categories, coordinator_email, deadline_quote, is_projected,"
            " source_as_of, deadline_evidence_url, main_info_url, issues, verify_state,"
            " imported_at, organizer, sponsor_required, sponsor_url, sponsor_cost,"
            " sponsor_quote)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(event_id) DO UPDATE SET"
            "  conference_key=excluded.conference_key, name=excluded.name, url=excluded.url,"
            "  city=excluded.city, state_province=excluded.state_province,"
            "  country=excluded.country, edition=excluded.edition, deadline=excluded.deadline,"
            "  submission_url=excluded.submission_url, cfp_model=excluded.cfp_model,"
            "  status=excluded.status, overview=excluded.overview,"
            "  categories=excluded.categories, coordinator_email=excluded.coordinator_email,"
            "  deadline_quote=excluded.deadline_quote, is_projected=excluded.is_projected,"
            "  source_as_of=excluded.source_as_of,"
            "  deadline_evidence_url=excluded.deadline_evidence_url,"
            "  main_info_url=excluded.main_info_url, issues=excluded.issues,"
            "  imported_at=excluded.imported_at,"
            "  organizer=excluded.organizer,"
            "  sponsor_required=excluded.sponsor_required,"
            "  sponsor_url=excluded.sponsor_url,"
            "  sponsor_cost=excluded.sponsor_cost,"
            # SPONSOR_QUOTE IS OURS (R20a) AND UPSTREAM SHIPS IT BLANK.
            # A plain excluded.sponsor_quote would wipe the quote we extracted on
            # every re-import. Only a non-empty incoming value may replace it.
            "  sponsor_quote=CASE WHEN excluded.sponsor_quote != ''"
            "                     THEN excluded.sponsor_quote"
            "                     ELSE grounding_facts.sponsor_quote END",
            (row.event_id, key, row.name, row.url, row.city, row.state, row.country,
             row.edition, row.deadline, row.submission_url, row.cfp_model,
             row.grounding_status, row.overview, row.categories, row.coordinator_email,
             row.deadline_quote, row.is_projected, row.source_as_of,
             row.deadline_evidence_url, row.main_info_url, "; ".join(row.issues),
             "unverified", now,
             row.organizer, row.sponsor_required, row.sponsor_url, row.sponsor_cost,
             row.sponsor_quote))
        stats["updated" if was else "inserted"] += 1

        if known:
            # Join the layers without altering any crawled value.
            store.db.execute("UPDATE conferences SET event_id=? WHERE key=? AND"
                             " (event_id IS NULL OR event_id='')", (row.event_id, key))
            canonical = registry.resolve(row.market) if row.market else None
            if canonical:
                if store.add_market(key, canonical, "grounding"):
                    stats["markets_added"] += 1
            elif row.market:
                # Unknown label: do NOT invent a market. Surface it for a human decision.
                stats["unmapped_markets"][row.market] = \
                    stats["unmapped_markets"].get(row.market, 0) + 1
    store.db.commit()
    return stats


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
