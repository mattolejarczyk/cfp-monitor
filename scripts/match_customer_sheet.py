"""Match a customer sheet to our canonical rows, and say how sure we are and why.

Their sheets carry no key of ours, so every ingest of their validation feedback has to start
here. Built to run per market: point it at one exported sheet and the market our matching rows
live in.

METHOD - independent tests, calibrated, then voted

  CERTAIN tests. Each is definitive on its own and returns 100%:
    exact URL          their CONFERENCE URL is, character for character, one of ours
    unique domain      the domain resolves to exactly ONE row in our whole database, so a
                       domain match cannot be anything else. The exclusion is the proof: no
                       other row of ours could claim it.
    name + city + date  three independent facts agreeing is not a coincidence

  SUPPORTING tests vote, weighted by precision MEASURED against anchor rows rather than
  assumed: domain+position, domain+name, domain+date, domain+city, exact name, name+city.

  SEQUENCE POSITION. Where the customer's list is an export of ours (or the reverse), order
  carries information. Aligning on domain rather than name matters - their names are
  abbreviations of ours, and aligning on names produced confidently wrong pairs.

EDITIONS ARE NOT AMBIGUITY. Two of our rows for the same conference in different years are one
answer, not two. We collapse candidates by series (the canonical key with its leading year
removed) and choose the edition whose date sits closest to theirs. The customer's row often
tracks a concluded edition while we have moved to the next; that is normal and must not
suppress the match.

    python scripts/match_customer_sheet.py --sheet <export.csv> --market Utility \
        --db <db> --delivery <ALL_MARKETS.csv> -o <out.csv>
"""
from __future__ import annotations

import argparse
import csv
import difflib
import importlib.util
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
STOP = {"the", "and", "of", "for", "on", "in", "a", "an", "conference", "summit", "expo",
        "exhibition", "congress", "forum", "show", "annual", "international", "week", "event"}


def host(u: str) -> str:
    h = (urlparse((u or "").strip()).netloc or "").lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    p = h.split(".")
    return ".".join(p[-3:]) if len(p) > 2 and p[-2] in ("co", "com", "org") else \
        ".".join(p[-2:]) if len(p) > 1 else h


def toks(n: str) -> set[str]:
    n = re.sub(r"\b(19|20)\d{2}\b", " ", (n or "").lower())
    n = re.sub(r"\([^)]*\)", " ", n)
    return {w for w in re.sub(r"[^a-z0-9]+", " ", n).split() if w not in STOP and len(w) > 1}


def sim(a: str, b: str) -> float:
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return max(len(ta & tb) / len(ta | tb),
               SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio() * 0.9)


def pdate(s: str):
    s = (s or "").strip()
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s.split()[0], f).date()
        except (ValueError, IndexError):
            pass
    m = re.search(r"\b(20\d{2})\b", s)
    return date(int(m.group(1)), 7, 1) if m else None


def series(eid: str) -> str:
    """The conference across all years - the canonical key without its leading year."""
    return re.sub(r"^(19|20)\d{2}-", "", eid or "")


def norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def load_ours(db: str, delivery: str, market: str):
    spec = importlib.util.spec_from_file_location("_ar", ROOT / "scripts" / "apply_resolutions.py")
    ar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ar)

    class _S:
        path = db

    up2c, _ = ar._seed_map(_S())
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    canon = {r["event_id"]: dict(r) for r in con.execute(
        "select event_id, name, city, country, url, main_info_url from grounding_facts")}
    con.close()

    start, seq, seen = {}, [], set()
    with open(delivery, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            raw = (r.get("EVENT_ID") or "").strip()
            eid = up2c.get(raw, raw)
            if eid not in canon:
                continue
            start.setdefault(eid, r.get("START DATE") or r.get("CONFERENCE DATES") or "")
            if (r.get("Market") or "").strip().lower() == market.lower() and eid not in seen:
                seen.add(eid)
                seq.append(eid)
    return canon, start, seq


def main() -> int:
    ap = argparse.ArgumentParser(description="Match a customer sheet to our canonical rows.")
    ap.add_argument("--sheet", required=True, help="their exported CSV")
    ap.add_argument("--market", required=True, help="our market these rows belong to")
    ap.add_argument("--db", required=True)
    ap.add_argument("--delivery", required=True, help="ALL_MARKETS delivery, for dates and order")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--name-col", default="CONFERENCE")
    a = ap.parse_args()

    canon, start_of, seq = load_ours(a.db, a.delivery, a.market)

    # THEIR HEADERS CARRY TRAILING WHITESPACE. Reading without stripping returns empty for
    # every row and every name test then fails silently while the report looks clean.
    with open(a.sheet, encoding="utf-8-sig", newline="") as fh:
        rdr = csv.reader(fh)
        header = next(rdr)
        body = [r for r in rdr if any((c or "").strip() for c in r)]
    I = {(c or "").strip(): i for i, c in enumerate(header)}
    for need in (a.name_col, "CONFERENCE URL"):
        if need not in I:
            sys.exit(f"sheet has no {need!r} column - found {sorted(I)}")
    if not any((r + [""] * len(header))[I[a.name_col]].strip() for r in body):
        sys.exit("every name read as blank - refusing to report numbers built on nothing")

    CN, CU = I[a.name_col], I["CONFERENCE URL"]
    CL, CD = I.get("LOCATION"), I.get("START DATES")

    by_host, by_name, by_url = defaultdict(set), defaultdict(set), defaultdict(set)
    for eid, c in canon.items():
        for f in ("url", "main_info_url"):
            if h := host(c[f]):
                by_host[h].add(eid)
            if norm_url(c[f]):
                by_url[norm_url(c[f])].add(eid)
        if n := " ".join(sorted(toks(c["name"]))):
            by_name[n].add(eid)

    A = [host((r + [""] * len(header))[CU]) for r in body]
    B = [host(canon[e]["url"] or canon[e]["main_info_url"]) for e in seq]
    pos = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                pos[i1 + k] = seq[j1 + k]

    def one(s):
        return next(iter(s)) if len(s) == 1 else None

    def collapse(cands, td):
        """Editions of one conference are ONE answer. Pick the edition nearest their date."""
        if not cands:
            return None, ""
        if len({series(c) for c in cands}) > 1:
            return None, ""
        if len(cands) == 1:
            return next(iter(cands)), ""
        best, note = None, ""
        if td:
            dated = [(abs((td - d).days), c) for c in cands
                     if (d := pdate(start_of.get(c, "")))]
            if dated:
                best = min(dated)[1]
        best = best or max(cands)
        note = (f" We hold {len(cands)} editions of this conference; chose {best} as the one "
                f"nearest their date - the others are earlier editions, not other events.")
        return best, note

    rows_out = []
    votes = []
    for i, raw in enumerate(body):
        r = raw + [""] * (len(header) - len(raw))
        tn, tu = r[CN].strip(), r[CU].strip()
        tl = r[CL].strip() if CL is not None else ""
        td = pdate(r[CD]) if CD is not None else None
        h, tc = host(tu), (tl.split(",")[0].strip().lower() if tl else "")
        hs = by_host.get(h, set())

        def dfit(e, days):
            d = pdate(start_of.get(e, ""))
            return d and td and abs((td - d).days) <= days

        def cityfit(e):
            oc = (canon[e]["city"] or "").strip().lower()
            return bool(tc and oc and (tc in oc or oc in tc))

        v = {
            "exact URL": by_url.get(norm_url(tu), set()),
            "unique domain": hs if h and len(hs) >= 1 else set(),
            "name+city+date": {e for e in canon
                               if sim(tn, canon[e]["name"]) >= 0.7 and cityfit(e) and dfit(e, 21)},
            "domain+position": {pos[i]} if i in pos else set(),
            "domain+name": {e for e in hs if sim(tn, canon[e]["name"]) >= 0.5},
            "domain+date": {e for e in hs if dfit(e, 21)},
            "domain+city": {e for e in hs if cityfit(e)},
            "exact name": by_name.get(" ".join(sorted(toks(tn))), set()),
            "name+city": {e for e in canon if sim(tn, canon[e]["name"]) >= 0.7 and cityfit(e)},
        }
        votes.append((v, td, h, hs))

    # calibrate the supporting tests against anchors (domain AND position agreed)
    anchors = {i: one(v["domain+position"]) for i, (v, *_ ) in enumerate(votes)
               if one(v["domain+position"])}
    weight = {}
    for m in votes[0][0]:
        fired = agree = 0
        for i, anc in anchors.items():
            g, _ = collapse(votes[i][0][m], votes[i][1])
            if g:
                fired += 1
                agree += (series(g) == series(anc))
        weight[m] = (agree / fired) ** 2 if fired else 0.0
    print(f"anchors: {len(anchors)}    calibrated weights:")
    for m in sorted(weight, key=lambda x: -weight[x]):
        print(f"   {m:<16} {weight[m]:.2f}")

    CERTAIN = ("exact URL", "unique domain", "name+city+date")
    for i, raw in enumerate(body):
        r = raw + [""] * (len(header) - len(raw))
        v, td, h, hs = votes[i]

        # EVALUATE EVERY TEST, ALWAYS. Short-circuiting on the first certainty threw away the
        # fact that seven other tests also agreed - which is the evidence a reviewer actually
        # wants, and the only record of how each test performed. Certainty decides the SCORE;
        # it must not decide what gets reported.
        tally, who, silent, edition_note = defaultdict(float), defaultdict(list), [], ""
        fired_w = 0.0
        for m, cands in v.items():
            if m == "unique domain" and not (h and hs and len({series(e) for e in hs}) == 1):
                silent.append(m)          # the domain is shared, so it proves nothing here
                continue
            g, note = collapse(cands, td)
            if not g:
                silent.append(m)
                continue
            edition_note = edition_note or note
            fired_w += weight[m]
            tally[g] += weight[m]
            who[g].append(m)

        if not tally:
            rows_out.append(r + ["", "0%", "Every test abstained - nothing of ours shares this "
                                           "URL, domain, name, position, city or date."])
            continue

        ranked = sorted(tally.items(), key=lambda x: -x[1])
        best, score = ranked[0]
        proved = [m for m in CERTAIN if m in who[best]]

        if proved:
            conf = 100
            why = {"exact URL": f"their URL is character-for-character ours ({h})",
                   "unique domain": f"the domain {h} resolves to exactly one conference in our "
                                    f"database, so no other row could claim it",
                   "name+city+date": "name, city and date all agree - three independent facts"}
            head = f"CERTAIN via {proved[0]}: {why[proved[0]]}."
        else:
            # abstention is not disagreement - purity among the tests that actually fired
            purity = score / fired_w if fired_w else 0
            depth = min(1.0, len(who[best]) / 4.0)
            conf = max(3, min(99, int(100 * purity * (0.6 + 0.4 * depth))))
            head = "No single test is conclusive on its own."

        total = len(v)
        parts = [head,
                 f"{len(who[best])} of {total} tests agree: {', '.join(sorted(who[best]))}."]
        for other, _ in ranked[1:]:
            parts.append(f"Disagreeing: {', '.join(sorted(who[other]))} -> {other}.")
        if silent:
            parts.append(f"Silent ({len(silent)}): {', '.join(sorted(silent))}.")
        if edition_note:
            parts.append(edition_note.strip())
        rows_out.append(r + [best, f"{conf}%", " ".join(parts)])

    keep = [c for c in header if c.strip() != "EVENT_ID"]
    with open(a.output, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(keep + ["EVENT_ID", "Index_Confidence", "Index_Justification"])
        for r in rows_out:
            w.writerow([x for k, x in enumerate(r[:len(header)])
                        if header[k].strip() != "EVENT_ID"] + r[len(header):])

    band = defaultdict(int)
    for r in rows_out:
        n = int(r[-2].rstrip("%"))
        band["100%" if n == 100 else "90-99%" if n >= 90 else "70-89%" if n >= 70
             else "40-69%" if n >= 40 else "under 40%"] += 1
    print()
    for k in ("100%", "90-99%", "70-89%", "40-69%", "under 40%"):
        if band[k]:
            print(f"  {band[k]:>3}  {k}")
    print(f"\nwrote {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
