"""ACT-25 (2026-10-05): which events sit on a standard platform. READ-ONLY: the live database is opened with mode=ro, nothing is fetched, nothing is written.

    python experiments/platform_census/census.py [--db <cfp_monitor.db>]

For the events on the Cybersecurity and Utility market lists (identity.market_canonical_ids), classify the host of each cited address (event page, submission page, deadline evidence page) into a platform
FAMILY, count the events per family and show how the verifier already fares on them (verify_state and verify_basis). Two kinds of family: SUBMISSION platforms (the page is the call itself: Sessionize,
Pretalx, HotCRP, Microsoft CMT, Papercept...) and ORGANISER platforms (one company runs many events on one site: SecureWorld, Reuters Events, Informa, Gartner...). Result and recommendation:
experiments/platform_census/RESULT-platform-census.md."""
from __future__ import annotations

import argparse
import collections
import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SUBMISSION = ("Sessionize", "Microsoft CMT", "Papercept", "HotCRP", "Pretalx", "EasyChair", "MapYourShow", "Evessio", "Cvent", "Google Forms", "JotForm", "HubSpot forms")
FAMILIES = [("Sessionize", "sessionize.com"), ("Microsoft CMT", "cmt3.research.microsoft.com"), ("Papercept", "papercept.net"), ("HotCRP", "hotcrp.com"), ("Pretalx", "pretalx.com"),
            ("EasyChair", "easychair.org"), ("MapYourShow", "mapyourshow.com"), ("Evessio", "evessiocloud.com"), ("Cvent", "cvent.com"), ("Google Forms", "forms.gle"),
            ("Google Forms", "docs.google.com"), ("JotForm", "jotform.com"), ("HubSpot forms", "hsforms.com"),
            ("SecureWorld (organiser platform)", "secureworld.io"), ("Reuters Events (organiser platform)", "reutersevents.com"), ("Informa Connect (organiser platform)", "informaconnect.com"),
            ("Terrapinn (organiser platform)", "terrapinn.com"), ("SEMI (organiser platform)", "semi.org"), ("Gartner (organiser platform)", "gartner.com"),
            ("Black Hat / Informa Tech (organiser platform)", "blackhat.com"), ("DMG Events (organiser platform)", "dmgeventsconferences.com"), ("SPIE", "spie.org"),
            ("OWASP (chapter and event wiki)", "owasp.org"), ("OWASP (chapter and event wiki)", "owasp.de")]
URL_COLS = ("submission_url", "deadline_evidence_url", "main_info_url", "url")


def host_of(u: str) -> str:
    h = urlparse(u).netloc.lower() if u and u.startswith("http") else ""
    return h[4:] if h.startswith("www.") else h


def family_of(h: str) -> str:
    for name, dom in FAMILIES:
        if h == dom or h.endswith("." + dom):
            return name
    return ""


def census(rows: list[dict]) -> dict:
    """{family: {event_id: row}} over the rows, each event counted once per family."""
    fam: dict[str, dict] = collections.defaultdict(dict)
    for r in rows:
        for k in URL_COLS:
            f = family_of(host_of(r.get(k) or ""))
            if f:
                fam[f][r["event_id"]] = r
    return fam


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(Path(os.environ.get("LOCALAPPDATA", "")) / "CFP-Monitor" / "cfp_monitor.db"))
    a = ap.parse_args()
    from src.cfp_monitor.identity import market_canonical_ids
    ids = market_canonical_ids(a.db)
    con = sqlite3.connect(f"file:{a.db.replace(chr(92), '/')}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("select * from grounding_facts") if r["event_id"] in ids]
    con.close()
    fam = census(rows)
    print(f"events on the two customer market lists: {len(rows)}")
    print(f"{'family':48} {'events':>6} {'date-proven':>11}  verify_state / verify_basis")
    seen = set()
    for f, evs in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        seen |= set(evs)
        vs = collections.Counter((r["verify_state"], r.get("verify_basis") or "") for r in evs.values())
        dated = sum(1 for r in evs.values() if r["verify_state"] == "verified" and r.get("verify_basis") == "date")
        print(f"{f:48} {len(evs):6d} {dated:11d}  {dict(vs)}")
    sub = {e for f in SUBMISSION for e in fam.get(f, {})}
    print(f"events on at least one named family: {len(seen)} of {len(rows)}; with a submission page on a submission platform: {sum(1 for r in rows if family_of(host_of(r.get('submission_url') or '')) in SUBMISSION)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
