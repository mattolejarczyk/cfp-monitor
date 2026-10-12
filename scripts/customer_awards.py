"""Is EVERY award on the two customer AWARDS sheets in our research queue - and if not, put it there (ACT-67). Dry run unless --apply; always exits 0.

    python scripts/customer_awards.py [--today D] [--sheets-dir <dir>] [--markets-dir <dir>] [--out-dir <dir>] [--cap 30] [--apply [--live]]

WHY. The customers' sheets define the job: anything they track is researched. ACT-51 did this for the two CONFERENCE sheets only; the AWARDS sheets (Arnica `arnica-awards`, Utility Global
`utility-awards`) were fetched every week (weekly_intake fetches every client in customer_sheets.json) but never read by anything. On 2026-10-12 the customers listed 153 awards, 32 of them were
not on the Awards page and 30 were not on `Markets/Awards_input.csv` at all (the awards research queue). This is the awards sibling of customer_coverage.py + customer_auto_add.py in one script.

THE ANSWER, per customer award (the newest snapshot of the sheet, read from files: awards are not loaded into the database):
  * IN_QUEUE      a live (not DUP_OF) row of `Awards_input.csv` for the customer's market has the same NAME KEY (case, '&', parentheses and years ignored), or the same SUBMISSION URL
                  (scheme, 'www', fragment and trailing slash ignored; the query STAYS, so ?AwardID=807 and ?AwardID=808 differ). A URL counts only when it has a path or query (a bare
                  website says nothing about which award) and no other award of the customer's own sheet uses it under another name.
  * WRONG_MARKET  only a row of the OTHER market has it: researched, but the customer's page will not show it (the Awards page is built per market). Added as a MARKET SIBLING row (operator ruling
                  2026-10-12: the customer's sheet is the source of truth): a copy of the other market's row with Market set to this customer's and DUP_OF = MARKET_SIBLING. The audit skips a DUP_OF row (the
                  award is researched ONCE); weekend_import.add_market_siblings then ships the researched row under both markets and import_awards adds the second award_markets membership.
  * EXCLUDED      each with its reason, never silent: the row is in the operator's ledger docs/operations/customer_not_researched.csv; the only row it matches is labelled DUP_OF.
  * NOT_IN_QUEUE  none of the above.
Also reported (information only, nothing is changed): every DUP_OF-labelled input row that the customer lists as a row of its own with its own priority and dates.

THE GATE for auto-add (each HOLD names its reason; HOLD rows are listed, never changed): no name; a name already on the list (exact, case-insensitive, any market); the same award twice on the
customer's own sheet (the first is added); WRONG_MARKET whose primary row cannot be found (a person decides); more than --cap (30) ADD rows for one market in one run
(the sheet changed shape or the matching broke: that market adds NOTHING). Rows are appended by scripts/add_customer_rows.write_with_proof (the existing writer: timestamped backup first, .tmp,
read-back proof that the old rows are unchanged and exactly the new ones were added, then replace) with a BLANK EVENT_ID_CANON. An id is NEVER minted: a new award waits for an id upstream gives
(draft request below), is then stamped with scripts/stamp_given_ids.py --awards, and loads as a new award on the next Friday import (weekend_import.py --new-awards).

OUTPUT (out-dir, default runs_out/qa/<today>): awards_coverage.json/.md, awards_proposed_additions.csv, awards_auto_add.json/.md, request_to_upstream_awards_<today>.md (a DRAFT; the operator
sends it, code sends nothing). stdout, read by scripts/weekend_recap.py:
    AWARDS COVERAGE: <n> of <m> customer awards are on the research input list; <k> are NOT; <w> only under the other market; <e> excluded with a reason
    AWARDS COVERAGE NOT IN QUEUE: <first five names>            (only when k > 0)
    AWARDS AUTOADD: mode=dry-run|applied; <a> to add|added, <h> held for a person, <x> waiting for an id; <k> customer awards NOT in the queue after the step
    AWARDS AUTOADD HELD: <first five names>                     (only when h > 0)
    AWARDS AUTOADD NOT PICKED UP: <first five names>            (only when applied and k > 0)
or `AWARDS COVERAGE: UNKNOWN - <why>` when an input cannot be read. --apply refuses the live Markets folder unless --live is given (the reviewer's switch)."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import add_customer_rows as acr                              # noqa: E402
from src.cfp_monitor import qa_report                                     # noqa: E402

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
SNAPSHOTS = MARKETS / "customer_snapshots"
NOT_RESEARCHED = ROOT / "docs" / "operations" / "customer_not_researched.csv"
# config key (customer_sheets.json, kind "awards") -> the market whose page shows it, and how SOURCE_SHEET names the sheet on the input list ("Arnica:7")
CLIENTS = {"arnica-awards": {"market": "Cybersecurity", "label": "Arnica", "short": "arnica"},
           "utility-awards": {"market": "Utility", "label": "Utility Global", "short": "utility"}}
CAP_PER_MARKET = 30
PROPOSE_COLS = ["client", "sheet_row", "award", "submission_url", "location", "priority", "customer_status", "customer_deadline", "market", "note"]
SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu"}
SIBLING = "MARKET_SIBLING"          # DUP_OF value of a row that says 'the same award, also for the customer of THIS market' (see weekend_import.award_siblings); the audit skips it, the import adds a membership


# ============================================================================ reading
def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def name_key(text: str) -> str:
    """A name with case, '&', anything in parentheses and any 20xx year removed: 'Grist 50 (2026)' and 'Grist 50 2026' and 'grist 50' are one key."""
    s = tidy(text).lower().replace("&", " and ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"(?<!\d)20\d\d(?!\d)", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r" (?:2|20|202)$", "", s)                           # the customer's sheet cuts a few names mid-year: 'Sustainability Leaders Awards (Edie) 2'


def url_key(url: str) -> str:
    """scheme, 'www.', fragment and a trailing slash dropped; the QUERY is kept (an award id may live in it). '' for a bare website (no path, no query)."""
    u = re.sub(r"^https?://(www\.)?", "", tidy(url).lower()).split("#")[0].rstrip("/")
    return u if ("/" in u or "?" in u) else ""


def registered_domain(url: str) -> str:
    u = tidy(url)
    host = (urlparse(u if "//" in u else "//" + u).hostname or "").lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) < 2:
        return host
    keep = 3 if len(parts) >= 3 and parts[-2] in SECOND_LEVEL and len(parts[-1]) == 2 else 2
    return ".".join(parts[-keep:])


def sheet_rows(path: Path, client: str) -> list[dict]:
    """The customer's awards sheet as plain dicts. STATUS is `STATUS` (Arnica) or `SUBMISSION STATUS` (Utility Global): the two customers name it differently."""
    out = []
    for i, r in enumerate(read_csv(path), start=2):                        # row 1 is the header
        name = tidy(r.get("AWARD"))
        out.append({"client": client, "sheet_row": i, "name": name, "url": tidy(r.get("SUBMISSION URL")), "location": tidy(r.get("LOCATION")),
                    "priority": tidy(r.get("PRIORITY")), "status": tidy(r.get("STATUS") or r.get("SUBMISSION STATUS")),
                    "deadline": tidy(r.get("SUBMISSION DEADLINE")), "event_date": tidy(r.get("EVENT DATE"))})
    return [r for r in out if r["name"] or r["url"]]                        # a wholly blank sheet line is not an award


def newest_sheet(sheets_dir: Path, client: str) -> Path | None:
    """<dir>/<client>/<client>_<stamp>.csv (the snapshot store; newest by name) or <dir>/<client>.csv (a hand-placed copy)."""
    folder = Path(sheets_dir) / client
    snaps = sorted(folder.glob(f"{client}_*.csv")) if folder.is_dir() else []
    if snaps:
        return snaps[-1]
    flat = Path(sheets_dir) / f"{client}.csv"
    return flat if flat.exists() else None


def load_ledger(path: Path) -> list[dict]:
    return read_csv(path) if Path(path).exists() else []


def customer_index(sheets_dir: Path = SNAPSHOTS) -> dict | None:
    """Every award on the customers' two awards sheets (newest snapshots), as {'names': {name key}, 'urls': {url key}}; None when a snapshot cannot be read (the caller then keeps everything).
    Used by the page builders to decide that a row the customer LISTS stays on the page, whatever type our own research gave it (operator ruling 2026-10-12: the customer's sheet is the source of truth)."""
    names: set[str] = set()
    urls: set[str] = set()
    try:
        for client in CLIENTS:
            p = newest_sheet(Path(sheets_dir), client)
            if p is None:
                return None
            for r in sheet_rows(p, client):
                if name_key(r["name"]):
                    names.add(name_key(r["name"]))
                if url_key(r["url"]):
                    urls.add(url_key(r["url"]))
    except Exception:                                                        # noqa: BLE001
        return None
    return {"names": names, "urls": urls} if names else None


def is_listed(index: dict | None, name: str, *urls: str) -> bool:
    """Is this page row an award the customers list? By name key, else by a deep submission/main URL. Never joins on an id."""
    if not index:
        return False
    k = name_key(name)
    if k and k in index["names"]:
        return True
    return any(url_key(u) and url_key(u) in index["urls"] for u in urls)


# ============================================================================ the question
def build_queue(inp: list[dict]) -> dict:
    """Per market: live rows (name keys, URL keys) and DUP_OF rows, from Awards_input.csv. A row with no OPPORTUNITY_TYPE 'Awards' is still a listing of that name."""
    q: dict = {"live": {}, "dup": {}, "names": set()}
    for r in inp:
        market = (r.get("Market") or "").strip()
        nm, k = tidy(r.get("CONFERENCE")), name_key(r.get("CONFERENCE"))
        urls = {url_key(r.get("SUBMISSION URL")), url_key(r.get("CONFERENCE URL"))} - {""}
        q["names"].add(nm.lower())
        bucket = q["dup"] if (r.get("DUP_OF") or "").strip() not in ("", SIBLING) else q["live"]      # a market sibling IS a live listing for its market
        d = bucket.setdefault(market, {"names": {}, "urls": {}})
        d["names"].setdefault(k, (nm, (r.get("DUP_OF") or "").strip()))
        for u in urls:
            d["urls"].setdefault(u, (nm, (r.get("DUP_OF") or "").strip()))
    return q


def classify(row: dict, market: str, queue: dict, ledger: list[dict], url_use: dict[str, set[str]]) -> tuple[str, str, str]:
    """-> (verdict, why, the input row it matched). verdict: IN_QUEUE | WRONG_MARKET | EXCLUDED | NOT_IN_QUEUE."""
    k, u = name_key(row["name"]), url_key(row["url"])
    for L in ledger:
        if (L.get("client") or "").strip().lower() != row["client"]:       # the ledger is per sheet: a ruling about the CONFERENCE sheet's 'arnica' / 'utility' row says nothing about an awards row
            continue
        if (name_key(L.get("event_name")) == k and k) or (u and url_key(L.get("url") or "") == u):
            return "EXCLUDED", f"operator's ledger (customer_not_researched.csv): {L.get('reason', '')} (ruled by {L.get('ruled_by', '?')} on {L.get('ruled_on', '?')})", ""
    url_ok = bool(u) and len(url_use.get(u, set())) <= 1             # a URL shared by several differently-named awards of the customer's own sheet names a family page, not one award
    live, dup = queue["live"].get(market, {"names": {}, "urls": {}}), queue["dup"].get(market, {"names": {}, "urls": {}})
    if k and k in live["names"]:
        return "IN_QUEUE", "by name", live["names"][k][0]
    if url_ok and u in live["urls"]:
        return "IN_QUEUE", "by submission URL", live["urls"][u][0]
    for other, d in queue["live"].items():
        if other == market:
            continue
        hit = d["names"].get(k) if k else None
        hit = hit or (d["urls"].get(u) if url_ok else None)
        if hit:
            return "WRONG_MARKET", f"on the input list only under {other} (the customer's {market} page will not show it)", hit[0]
    hit = dup["names"].get(k) if k else None
    hit = hit or (dup["urls"].get(u) if url_ok else None)
    if hit:
        return "EXCLUDED", f"the only row it matches is labelled DUP_OF '{hit[1]}' (researched as that award; the audit skips this row)", hit[0]
    return "NOT_IN_QUEUE", "no input row has its name or its submission URL", ""


def dup_listed_separately(rows: list[dict], inp: list[dict], market_of: dict[str, str]) -> list[dict]:
    """DUP_OF-labelled input rows that the customer's sheet lists as a row of its own (own priority, own dates). Information only."""
    by_key: dict[tuple[str, str], dict] = {}
    for r in rows:
        by_key.setdefault((market_of[r["client"]], name_key(r["name"])), r)
    out = []
    for r in inp:
        tgt = (r.get("DUP_OF") or "").strip()
        if not tgt or tgt == SIBLING:
            continue
        c = by_key.get(((r.get("Market") or "").strip(), name_key(r.get("CONFERENCE"))))
        if c:
            out.append({"input_row": tidy(r.get("CONFERENCE")), "dup_of": tgt, "client": c["client"], "customer_row": c["sheet_row"], "customer_priority": c["priority"] or "-",
                        "customer_deadline": c["deadline"] or "-", "customer_status": c["status"] or "-", "market": (r.get("Market") or "").strip()})
    return out


def check(sheets: dict[str, list[dict]], inp: list[dict], ledger: list[dict]) -> dict:
    queue = build_queue(inp)
    res: dict = {"in_queue": [], "wrong_market": [], "excluded": [], "not_in_queue": [], "dup_listed_separately": [], "customer_total": sum(len(v) for v in sheets.values())}
    market_of = {c: m["market"] for c, m in CLIENTS.items()}
    for client, rows in sheets.items():
        use: dict[str, set[str]] = {}
        for r in rows:
            u = url_key(r["url"])
            if u:
                use.setdefault(u, set()).add(name_key(r["name"]))
        for r in rows:
            verdict, why, matched = classify(r, market_of[client], queue, ledger, use)
            item = {**r, "market": market_of[client], "why": why, "input_row": matched}
            res[{"IN_QUEUE": "in_queue", "WRONG_MARKET": "wrong_market", "EXCLUDED": "excluded", "NOT_IN_QUEUE": "not_in_queue"}[verdict]].append(item)
    res["dup_listed_separately"] = dup_listed_separately([r for rows in sheets.values() for r in rows], inp, market_of)
    return res


def summary_lines(res: dict) -> list[str]:
    n, k, w, e = len(res["in_queue"]), len(res["not_in_queue"]), len(res["wrong_market"]), len(res["excluded"])
    lines = [f"AWARDS COVERAGE: {n} of {n + k + w} customer awards are on the research input list; {k} are NOT; {w} only under the other market; {e} excluded with a reason"]
    if w:
        lines.append("AWARDS COVERAGE WRONG MARKET: " + "; ".join(x["name"] for x in res["wrong_market"][:5]) + (f"; and {w - 5} more" if w > 5 else ""))
    if k:
        lines.append("AWARDS COVERAGE NOT IN QUEUE: " + "; ".join(x["name"] for x in res["not_in_queue"][:5]) + (f"; and {k - 5} more" if k > 5 else ""))
    return lines


# ============================================================================ the gate
def new_input_row(item: dict, cols: list[str]) -> dict:
    """A blank-id Awards_input.csv row for a customer award. Only what the customer's sheet states about the award; their dates and status stay on their sheet (research finds the cycle)."""
    row = {c: "" for c in cols}
    row["CONFERENCE"] = item["name"]
    row["SUBMISSION URL"] = item["url"]
    row["LOCATION"] = item["location"] if "no physical event" not in item["location"].lower() and "not applicable" not in item["location"].lower() else ""
    row["Market"] = item["market"]
    row["OPPORTUNITY_TYPE"] = "Awards"
    row["RESEARCH STATUS"] = "Needs Verification"
    row["SOURCE_SHEET"] = f"{CLIENTS[item['client']]['label']}:{item['sheet_row']}"
    row["OPERATOR"] = registered_domain(item["url"])
    return row


def gate(res: dict, inp: list[dict], cols: list[str], cap: int) -> tuple[list[tuple[dict, dict]], list[tuple[dict, str]]]:
    """-> ([(customer item, new input row)] to ADD, [(customer item, HOLD reason)])."""
    add: dict[str, list[tuple[dict, dict]]] = {}
    hold: list[tuple[dict, str]] = []
    listed = {tidy(r.get("CONFERENCE")).lower() for r in inp}
    seen_keys: dict[tuple[str, str], str] = {}
    for item in res["not_in_queue"]:
        if not name_key(item["name"]):
            hold.append((item, "no name: nothing to research"))
            continue
        if item["name"].lower() in listed:
            hold.append((item, "a row with this exact name is already on the input list"))
            continue
        key = (item["market"], name_key(item["name"]))
        if key in seen_keys:
            hold.append((item, f"the customer lists this award twice on their own sheet (also '{seen_keys[key]}'); the first is added"))
            continue
        seen_keys[key] = item["name"]
        add.setdefault(item["market"], []).append((item, new_input_row(item, cols)))
    sib: dict[str, list[tuple[dict, dict]]] = {}
    for item in res["wrong_market"]:
        # OPERATOR RULING 2026-10-12: the customer's sheet is the source of truth; an award on it is shown to that customer. The award already has a row under the other market, so it is NOT
        # researched twice: the new row is a MARKET SIBLING (DUP_OF = MARKET_SIBLING, same name and id) that tells the import to show the same record under this market too.
        k, u = name_key(item["name"]), url_key(item["url"])
        survivor = next((r for r in inp if (r.get("Market") or "").strip() != item["market"] and (r.get("DUP_OF") or "").strip() in ("", SIBLING)
                         and ((k and name_key(r.get("CONFERENCE")) == k) or (u and u in {url_key(r.get("SUBMISSION URL")), url_key(r.get("CONFERENCE URL"))}))), None)
        if survivor is None or (survivor.get("DUP_OF") or "").strip():
            hold.append((item, "listed under the other market but its primary row could not be found: a person decides"))
            continue
        row = dict(survivor)
        row.update({"Market": item["market"], "DUP_OF": SIBLING, "REFRESH_SKIP": "", "STATUS": "", "PRIORITY": "", "SOURCE_SHEET": f"{CLIENTS[item['client']]['label']}:{item['sheet_row']}"})
        row = {c: row.get(c, "") for c in cols}
        sib.setdefault(item["market"], []).append((item, row))
    out: list[tuple[dict, dict]] = []
    for pairs in sib.values():
        out.extend(pairs)
    for market, pairs in add.items():
        if len(pairs) > cap:
            for item, _ in pairs:
                hold.append((item, f"cap: {len(pairs)} awards for {market} this run, above {cap}: the sheet changed shape or the matching broke; nothing is added for this market"))
        else:
            out.extend(pairs)
    return out, hold


def waiting_for_id(inp: list[dict]) -> list[dict]:
    """Live input rows with a blank EVENT_ID_CANON (not DUP_OF): researched, but never loaded as a new award until upstream gives the id."""
    return [{"market": (r.get("Market") or "").strip(), "name": tidy(r.get("CONFERENCE")), "url": tidy(r.get("SUBMISSION URL") or r.get("CONFERENCE URL"))}
            for r in inp if not (r.get("EVENT_ID_CANON") or "").strip() and not (r.get("DUP_OF") or "").strip()]


def request_draft(today: str, waiting: list[dict]) -> str:
    L = [f"DRAFT request to upstream (awards), {today} - the operator reads and sends it; nothing is sent by code.", "",
         "Please give us your permanent EVENT_ID for each award below. They are on the customers' own awards sheets, so we research them under their submission URL and hold them back from the "
         "load until we have the id. If one is the same award as one you already track, tell us which id.", "",
         f"Awards without an id ({len(waiting)}):", "", "| market | award | submission URL |", "|---|---|---|"]
    L += [f"| {w['market']} | {w['name']} | {w['url'] or '-'} |" for w in waiting]
    return "\n".join(L) + "\n"


# ============================================================================ run
def markdown(res: dict, summary: list[str], held: list[tuple[dict, str]], added: list[dict], mode: str, today: str) -> str:
    L = [f"# Customer awards: coverage and automatic add ({mode}), {today}", "", "Read from the newest snapshot of each customer awards sheet (scripts/customer_awards.py).", ""]
    L += [f"- {s}" for s in summary] + [""]

    def table(title, items, cols):
        out = [f"## {title} ({len(items)})", ""]
        if items:
            out += ["| " + " | ".join(h for h, _ in cols) + " |", "|" + "---|" * len(cols)]
            out += ["| " + " | ".join(str(i.get(k) or "-") for _, k in cols) + " |" for i in items]
        else:
            out += ["None."]
        return out + [""]
    base = [("client", "client"), ("award", "name"), ("sheet row", "sheet_row"), ("priority", "priority"), ("status", "status"), ("deadline", "deadline")]
    L += table("NOT on the research input list", res["not_in_queue"], base)
    L += table("Only under the other market", res["wrong_market"], base + [("why", "why")])
    L += table("Excluded, each with its reason", res["excluded"], base + [("why", "why")])
    L += ["## HOLD FOR A PERSON (not added)", ""] + ([f"- {i['name']} ({i['client']}): {r}" for i, r in held] or ["None."]) + [""]
    L += ["## ADD" + (" (added)" if mode == "applied" else " (would be added)"), ""] + ([f"- {a['Market']}: {a['CONFERENCE']} | {a['SUBMISSION URL'] or 'no URL'}" for a in added] or ["None."]) + [""]
    L += table("DUP_OF-labelled input rows the customer lists as rows of their own (information; the audit skips the labelled row)", res["dup_listed_separately"],
               [("input row", "input_row"), ("DUP_OF", "dup_of"), ("client", "client"), ("sheet row", "customer_row"), ("their priority", "customer_priority"),
                ("their deadline", "customer_deadline"), ("their status", "customer_status")])
    return "\n".join(L)


def run(today: str, sheets_dir: Path, markets_dir: Path, ledger_path: Path, out_dir: Path, cap: int, apply: bool) -> tuple[list[str], int]:
    """-> (stdout lines, 0). A missing input is reported on the first line, never raised."""
    inp_path = Path(markets_dir) / "Awards_input.csv"
    if not inp_path.exists():
        return [f"AWARDS COVERAGE: UNKNOWN - the awards input list was not found ({inp_path})"], 0
    sheets: dict[str, list[dict]] = {}
    for client in CLIENTS:
        p = newest_sheet(sheets_dir, client)
        if p is None:
            return [f"AWARDS COVERAGE: UNKNOWN - no snapshot of the {client} sheet in {sheets_dir} (the weekly intake fetches it)"], 0
        sheets[client] = sheet_rows(p, client)
        if not sheets[client]:
            return [f"AWARDS COVERAGE: UNKNOWN - the {client} snapshot {p.name} has no award rows"], 0
    cols, inp, _bom, _crlf = acr.read_input(inp_path)
    ledger = load_ledger(ledger_path)
    res = check(sheets, inp, ledger)
    summary = summary_lines(res)
    pairs, held = gate(res, inp, cols, cap)
    added_rows = [r for _, r in pairs]
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "awards_proposed_additions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PROPOSE_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows({"client": i["client"], "sheet_row": i["sheet_row"], "award": i["name"], "submission_url": i["url"], "location": i["location"], "priority": i["priority"],
                     "customer_status": i["status"], "customer_deadline": i["deadline"], "market": i["market"], "note": "proposed by customer_awards.py: " + i["why"]} for i, _ in pairs)
    notes: list[str] = []
    after_k, left = len(res["not_in_queue"]), [x["name"] for x in res["not_in_queue"]]
    waiting = waiting_for_id(inp)
    if apply:
        by_market: dict[str, list[dict]] = {}
        for r in added_rows:
            by_market.setdefault(r["Market"], []).append(r)
        if by_market:
            bak = acr.write_with_proof(inp_path, cols, inp, [r for rows in by_market.values() for r in rows], _bom, _crlf)
            notes.append(f"{inp_path.name}: {len(added_rows)} appended, backup {bak.name}")
        _, inp_after, _, _ = acr.read_input(inp_path)
        res_after = check(sheets, inp_after, ledger)
        after_k, left = len(res_after["not_in_queue"]), [x["name"] for x in res_after["not_in_queue"]]
        waiting = waiting_for_id(inp_after)
    mode = "applied" if apply else "dry-run"
    clean = {k: v for k, v in res.items()}
    (out_dir / "awards_coverage.json").write_text(json.dumps({"today": today, "summary": summary, **clean}, indent=1, ensure_ascii=True), encoding="utf-8")
    auto = {"today": today, "mode": mode, "to_add": [{"market": r["Market"], "award": r["CONFERENCE"], "url": r["SUBMISSION URL"], "source_sheet": r["SOURCE_SHEET"]} for r in added_rows],
            "held": [{"name": i["name"], "client": i["client"], "sheet_row": i["sheet_row"], "reason": r} for i, r in held], "waiting_for_id": waiting,
            "not_in_queue_after": after_k, "applied": notes}
    (out_dir / "awards_auto_add.json").write_text(json.dumps(auto, indent=1, ensure_ascii=True), encoding="utf-8")
    (out_dir / "awards_coverage.md").write_text(markdown(res, summary, held, added_rows, mode, today) + "\n", encoding="utf-8")
    (out_dir / "awards_auto_add.md").write_text(f"# Customer awards: automatic add ({mode}), {today}\n\n- ADD {len(added_rows)}, HOLD {len(held)}, waiting for an id {len(waiting)}, NOT in queue after the step {after_k}\n", encoding="utf-8")
    (out_dir / f"request_to_upstream_awards_{today}.md").write_text(request_draft(today, waiting + ([] if apply else [{"market": r["Market"], "name": r["CONFERENCE"], "url": r["SUBMISSION URL"]} for r in added_rows])), encoding="utf-8")
    verb = "added" if apply else "to add"
    lines = summary + [f"AWARDS AUTOADD: mode={mode}; {len(added_rows)} {verb}, {len(held)} held for a person, {len(waiting)} waiting for an id; {after_k} customer awards NOT in the queue after the step"]
    if held:
        lines.append("AWARDS AUTOADD HELD: " + "; ".join(i["name"] for i, _ in held[:5]) + (f"; and {len(held) - 5} more" if len(held) > 5 else ""))
    if apply and after_k > 0:
        lines.append("AWARDS AUTOADD NOT PICKED UP: " + "; ".join(left[:5]) + (f"; and {len(left) - 5} more" if len(left) > 5 else ""))
    return lines, 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--sheets-dir", default=str(SNAPSHOTS), help="the snapshot store (<dir>/<client>/<client>_<stamp>.csv) or a folder of <client>.csv copies")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--ledger", default=str(NOT_RESEARCHED))
    ap.add_argument("--out-dir", default="", help="default runs_out/qa/<today>")
    ap.add_argument("--cap", type=int, default=CAP_PER_MARKET)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--live", action="store_true", help="allow --apply on the live Markets folder (the reviewer's switch)")
    a = ap.parse_args()
    try:
        if a.apply and Path(a.markets_dir).resolve() == MARKETS.resolve() and not a.live:
            print("AWARDS AUTOADD: REFUSED - --apply on the live Markets folder needs --live (reviewer's switch); nothing written")
            return 0
        out = Path(a.out_dir) if a.out_dir else qa_report.QA_ROOT / a.today
        lines, _ = run(a.today, Path(a.sheets_dir), Path(a.markets_dir), Path(a.ledger), out, a.cap, a.apply)
        print("\n".join(lines))
    except Exception as e:                                                  # a step before the research must never stop the Friday or Saturday job
        print(f"AWARDS COVERAGE: UNKNOWN - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
