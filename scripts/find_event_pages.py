"""Chase the CURRENT homepage for events whose MAIN_INFO_URL / CONFERENCE URL is dead.

find_replacement_links chases SUBMISSION pages, so these were never handed to it. A dead event
homepage is a different problem with a different tell: the BBI cases showed that a domain
returning 404 over HTTPS often still REDIRECTS over plain HTTP to its successor. That is the
site telling us where it went, which is why it counts as a correction rather than a guess (2.5).

Proposes nothing it cannot corroborate. A 200 is not enough - a parked domain returns 200. The
page title (or visible text) must share distinctive words with the conference name, otherwise
this reports "no successor found" and the row goes to upstream as an R1/blank case.

Writes a CSV for the hand-back. Writes NOTHING to the database: MAIN_INFO_URL and CONFERENCE URL
are upstream's fields (contract section 3).
"""
import csv
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, r"C:\Users\matts\cfp-monitor")

import sqlite3

DB = r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db"
OUT = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\homepages_20260828.csv")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
STOP = {"the", "and", "for", "conference", "summit", "expo", "show", "annual", "international",
        "congress", "forum", "world", "meeting", "convention", "week", "2026", "2027", "usa",
        "europe", "north", "america", "of", "on", "in", "at", "&"}


def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def fetch(u, timeout=25):
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=ssl._create_unverified_context()) as r:
            return r.status, r.url, r.read(250_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, u, ""
    except Exception as e:                                            # noqa: BLE001
        return 0, u, f"__ERR__{type(e).__name__}"


def title_of(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())[:120] if m else ""


con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
dead = {r[0] for r in con.execute("select url from link_checks where state='dead'")}

# Only the EVENT-PAGE fields. Submission links were covered by find_replacement_links; dead
# evidence URLs are an R1 conversation, not a homepage hunt.
targets = {}
for r in con.execute("select * from grounding_facts"):
    for f in ("main_info_url", "url"):
        u = (r[f] or "").strip()
        if u in dead:
            targets.setdefault(u, {"name": r["name"] or r["event_id"],
                                   "event_id": r["event_id"], "fields": set()})["fields"].add(f)
print(f"{len(targets)} distinct dead event-page URL(s) to chase\n")

rows = []
for i, (u, meta) in enumerate(sorted(targets.items()), 1):
    host = urlparse(u).netloc
    bare = host.replace("www.", "")
    name_words = words(meta["name"])
    print(f"[{i}/{len(targets)}] {meta['name'][:52]}")
    print(f"    dead: {u[:88]}")

    try:
        socket.gethostbyname(host)
    except Exception:                                                 # noqa: BLE001
        print("    domain does not resolve - genuinely gone")
        rows.append({"CONFERENCE": meta["name"], "EVENT_ID": meta["event_id"],
                     "FIELDS": " + ".join(sorted(meta["fields"])), "DEAD URL": u,
                     "OUTCOME": "Domain does not resolve", "PROPOSED URL": "",
                     "HTTP": "", "TITLE": "", "WHY": "DNS failure - needs a new address"})
        continue

    best = None
    # Plain HTTP first: that is the rung that exposed both BBI migrations.
    for cand in (f"http://www.{bare}/", f"http://{bare}/", f"https://www.{bare}/",
                 f"https://{bare}/"):
        status, final, html = fetch(cand)
        if status != 200 or html.startswith("__ERR__"):
            continue
        t = title_of(html)
        overlap = name_words & (words(t) | words(html[:4000]))
        moved = urlparse(final).netloc.replace("www.", "") != bare
        if overlap:
            best = (final, status, t, sorted(overlap), moved)
            break
        if best is None:
            best = (final, status, t, [], moved)   # keep as a weak fallback

    if best and best[3]:
        final, status, t, ov, moved = best
        # R3: "never substitute a shallower URL to obtain a 200". If the dead URL had a real
        # path and the candidate is a bare root, we have found the ORGANISATION, not the event
        # page - amp.org instead of the AMP Annual Meeting, ces.tech instead of CES Unveiled.
        # Matching on one generic token (amp, ces, dia) proves only that much.
        # PATH DEPTH IS THE WRONG TEST. It demoted AM Forum, whose domain is dedicated to the
        # event so its ROOT IS the event page - title "11th AM Forum 2027 - Leading user
        # conference on industrial Additive Manufacturing". Meanwhile amp.org, whose root is
        # "Home - Association for Molecular Pathology", is genuinely the organisation.
        #
        # The discriminator is whether the TITLE names the event. AMP matched only on body
        # text; a page that is really this event says so in its title.
        title_hits = name_words & words(t)
        dead_depth = len([p for p in urlparse(u).path.split("/") if p])
        new_depth = len([p for p in urlparse(final).path.split("/") if p])
        shallower = dead_depth > 0 and new_depth == 0

        if len(title_hits) < 2:
            kind = "Organisation page only - NOT the event page"
            why = (f"the page TITLE does not name this event (title: {t[:60]!r}); the event "
                   f"name matched only in body text on {', '.join(sorted(ov)[:4])}"
                   + (f", and it resolves to the site root while the dead URL had {dead_depth} "
                      f"path segment(s)" if shallower else "")
                   + ". This is the organisation, not this event - upstream must locate the "
                     "event page.")
            print(f"    LEAD ONLY: {final[:74]}")
            print(f"       title does not name the event: {t[:56]!r}")
        else:
            kind = "Successor host found" if moved else "Same host now responds"
            why = (f"the page TITLE names this event ({t[:70]!r}), matching on "
                   f"{', '.join(sorted(title_hits)[:5])}")
            print(f"    REPLACEMENT: {final[:70]}")
            print(f"       title={t[:56]!r} title-match {sorted(title_hits)[:4]}")
        rows.append({"CONFERENCE": meta["name"], "EVENT_ID": meta["event_id"],
                     "FIELDS": " + ".join(sorted(meta["fields"])), "DEAD URL": u,
                     "OUTCOME": kind, "PROPOSED URL": final, "HTTP": status, "TITLE": t,
                     "WHY": why})
    else:
        why = ("responds but nothing on the page matches the event name - possibly parked or "
               "resold" if best else "no variant returned a readable page")
        print(f"    no corroborated successor - {why}")
        rows.append({"CONFERENCE": meta["name"], "EVENT_ID": meta["event_id"],
                     "FIELDS": " + ".join(sorted(meta["fields"])), "DEAD URL": u,
                     "OUTCOME": "No corroborated successor", "PROPOSED URL": "",
                     "HTTP": best[1] if best else "", "TITLE": best[2] if best else "",
                     "WHY": why})

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    wtr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_ALL)
    wtr.writeheader()
    wtr.writerows(rows)

real = sum(1 for r in rows if r["PROPOSED URL"] and "Organisation page only" not in r["OUTCOME"])
leads = sum(1 for r in rows if "Organisation page only" in r["OUTCOME"])
none_ = len(rows) - real - leads
print(f"\n{real} corroborated event-page replacement(s)")
print(f"{leads} organisation-page lead(s) - NOT corrections, upstream must find the event page")
print(f"{none_} with no successor at all")
print(f"wrote {OUT}")
print("\nPROPOSALS ONLY. MAIN_INFO_URL and CONFERENCE URL are upstream's fields (section 3).")
