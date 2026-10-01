"""Offline re-score of the crawl-test pages with the new date reader (dates_v2). No network. Reads crawl_pages.json.
Compares OLD (verify.find_date + English-only date-near-call) with NEW (dates_v2.find_target + any_date_near_call) on the same text.
Writes rescore_dates.json.
"""
import json, re, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import dates_v2 as d2
from src.cfp_monitor.verify import find_date

KNOWN = {"ccus-expo.com": date(2026, 9, 9), "h2meet.com": date(2026, 9, 30), "actexpo.com": date(2026, 9, 10),
         "sans.org": date(2026, 5, 26), "blackhat.com": date(2026, 3, 23), "troopers.de": date(2026, 3, 31)}
MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
OLD_ANY = re.compile(rf"\b{MON}\s+\d{{1,2}}\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MON}|\b20\d\d-\d\d-\d\d\b", re.I)
OLD_CALL = re.compile(r"deadline|submission|submit|call for|abstract|proposal|cfp|due|closes?|speaker", re.I)


def old_near(text):
    return any(OLD_ANY.search(text[max(0, m.start() - 200): m.end() + 200]) for m in OLD_CALL.finditer(text))


def context(text, rx, radius=70):
    m = rx.search(text)
    return re.sub(r"\s+", " ", text[max(0, m.start() - radius): m.end() + radius]) if m else ""


pages = json.loads((HERE / "crawl_pages.json").read_text(encoding="utf-8"))
rows, sites = [], {}
for url, p in pages.items():
    host = p["site"]; text = p["text"] or ""; known = KNOWN[host]
    old_known = bool(text) and find_date(text, known)
    new_known = d2.find_target(text, known)
    old_n, new_n = old_near(text), d2.any_date_near_call(text)
    rows.append({"site": host, "rank": p["rank"], "tier": p["tier"][:2], "url": url, "chars": len(text),
                 "old_known": old_known, "new_known": new_known[0] if new_known else "", "new_form": new_known[1] if new_known else "",
                 "old_near": old_n, "new_near": new_n, "ctx": context(text, d2.CALLVOC) if new_n else ""})
    s = sites.setdefault(host, {"known": known.isoformat(), "old": False, "new": "", "pages": 0})
    s["pages"] += 1
    s["old"] = s["old"] or bool(old_known)
    order = ["with-year", "yearless", "yearless-noyr", "ambiguous", ""]
    if new_known and order.index(new_known[0]) < order.index(s["new"] or ""):
        s["new"] = new_known[0]
n = len(rows)
summ = {"pages": n, "pages_with_date_near_call": {"old": sum(r["old_near"] for r in rows), "new": sum(r["new_near"] for r in rows)},
        "pages_showing_known_deadline": {"old": sum(r["old_known"] for r in rows), "new": sum(bool(r["new_known"]) for r in rows)},
        "sites_known_deadline_found": {"old": sum(s["old"] for s in sites.values()), "new": sum(bool(s["new"]) for s in sites.values()), "of": len(sites)},
        "new_confidence_by_site": {h: s["new"] or "not found" for h, s in sites.items()}}
(HERE / "rescore_dates.json").write_text(json.dumps({"summary": summ, "pages": rows}, indent=1), encoding="utf-8")
print(json.dumps(summ, indent=1))
print("\nper page (site, rank, tier, old-near/new-near, known-deadline OLD -> NEW):")
for r in rows:
    print(f"  {r['site'][:14]:<14} {r['rank']:>2} {r['tier']} near {int(r['old_near'])}->{int(r['new_near'])}  known {int(r['old_known'])}->{r['new_known'] or '-':<14} {r['url'].split('/',3)[-1][:44]}")
print("\ncall-page dates seen near call wording (new reader):")
for r in rows:
    if r["tier"] == "P1" and r["ctx"]:
        print(f"  {r['site']}: ...{r['ctx'][:170]}...")
