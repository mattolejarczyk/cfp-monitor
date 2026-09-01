"""Build the customer review page from a delivery CSV.

    py build_review_page.py -i ALL_MARKETS_AUDITED_20260807.csv -o ../handoff-files/CFP_Review_20260807.html

Self-contained HTML: no server, no internet, no dependencies. Open it from disk.

DESIGN NOTES - why the page looks like this
-------------------------------------------
Driven by the customer's own words (VOICE_OF_CUSTOMER_REQUIREMENTS.md) and their
alert-trigger table, not by what is easy to render.

  "We have to go every week to look at their top conferences and find when they
   have updated the call for speakers."
  "When you've got dozens of clients all in different industries... now you're
   talking about hundreds of conferences."

So the landing state is NOT the full list. It is "what needs action this week".
Their alert table ranks a deadline under 30 days as HIGH priority, so that is the
default view; everything else is one click away.

Urgency is computed IN THE BROWSER against today's real date, never baked in.
That mirrors contract 2.2 - derive, do not mutate - so the page stays correct as
days pass instead of going stale the moment it is written.

Confidence is shown on every row because contract 7 says the customer's question
is "can I act on this without checking first?". A projected date that looks like
a confirmed one is the single most expensive thing this page could do.
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIELDS =['CONFERENCE', 'Market', 'CITY', 'STATE_PROVINCE', 'COUNTRY', 'FORMAT',
          'CONFERENCE DATES', 'START DATE', 'SUBMISSION DEADLINE', 'STATUS',
          'GROUNDING_CONFIDENCE', 'IS_PROJECTED', 'STATUS DETAILS', 'CONFERENCE URL',
          'SUBMISSION URL', 'CFP_SUBMISSION_URL', 'DEADLINE_EVIDENCE_URL',
          'DEADLINE_QUOTE', 'TRACK', 'OPPORTUNITY_TYPE', 'MAIN_INFO_URL',
          'ORGANIZER', 'SPONSOR_REQUIRED', 'SPONSOR_URL', 'SPONSOR_COST', 'SOURCE_AS_OF',
          'SPONSOR_QUOTE',
          # THIS LIST IS A WHITELIST, and `build` reads every row through it - a column absent
          # here is silently empty downstream no matter what the delivery holds. Adding the
          # render without adding these two produced exactly that on 2026-09-01: the page
          # carried `"lq": ""` for ESF MENA while the delivery held the organiser's sentence.
          # `d.get(col, '')` looked defensive and was the thing hiding it.
          'LIFECYCLE_QUOTE', 'LIFECYCLE_EVIDENCE_URL']

MARKET_LABEL = {'robotics': 'Robotics', 'Robotics': 'Robotics', 'AdditiveMfg': 'Additive Mfg',
                'ConsumerElectronics': 'Consumer Electronics', 'BioMedTech': 'BioMedTech',
                'Cybersecurity': 'Cybersecurity', 'Semiconductor': 'Semiconductor',
                'Utility': 'Utility', 'Bioeconomy': 'Bioeconomy'}


DEFUNCT = re.compile(
    r'permanently ended|permanently concluded|no future editions|final edition|last edition|'
    r'discontinued|no longer (?:being )?(?:held|running)|has been cancell?ed|'
    r'ceased operations|will not (?:be held|return)|final year', re.I)

# A rotating event is not a dead one. EMO Hannover 2027 says "will not be held in
# Hannover... the EMO cycle dictates" - the series is alive, it just moves venue.
ROTATION = re.compile(r'cycle dictates|rotat|alternat|moves to|held instead in', re.I)


# R13 lives in src/cfp_monitor/lifecycle.py as of 2026-08-31. It was correct here, but living
# inside the page builder meant the gate, the weekly job and the client reconciliation could not
# ask the question - so STATUS went on being read from the file, and went stale. One
# implementation, imported by everything that needs it.
from src.cfp_monitor import lifecycle                      # noqa: E402
from src.cfp_monitor.lifecycle import edition_states       # noqa: E402,F401


def newest_check(db):
    """When the link picture was last refreshed, or None if it never was."""
    con = sqlite3.connect(db)
    try:
        row = con.execute('select max(checked_at) from link_checks').fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()
    return row[0] if row else None


def load_dead_links(path=None, db=None):
    """URLs a REAL BROWSER confirmed dead (scripts/recheck_dead_links.py).

    Never populate this from a plain-HTTP 404 alone - contract 5.2: 403s, timeouts and
    blocked pages are not disproof, and 5 of the delivery's apparent 404s loaded fine in a
    browser.

    PREFER --db. A CSV is a point-in-time export and goes stale silently: on 2026-08-12 the
    page was built from an Aug-8 export while link_checks had known since Aug-9 that a cited
    page was dead, and the link shipped to the customer on a row labelled Verified. Reading the
    table directly removes the failure mode rather than warning about it.

    The CSV path is kept for building a page from an export alone, and main() refuses when it
    is older than the newest check in the database.
    """
    if db:
        con = sqlite3.connect(db)
        try:
            return {r[0] for r in con.execute(
                "select url from link_checks where lower(state)='dead' and url is not null")}
        except sqlite3.OperationalError:
            return set()
        finally:
            con.close()
    if not path:
        return set()
    dead = set()
    with open(path, encoding='utf-8-sig', newline='') as h:
        head = h.readline()
        h.seek(0)
        if 'SUBMISSION URL' in head:
            for r in csv.DictReader(h):
                u = (r.get('SUBMISSION URL') or '').strip()
                if u:
                    dead.add(u)
        else:
            dead = {ln.strip() for ln in h if ln.strip().startswith('http')}
    return dead


def load_checks(path):
    """Our own verification of each deadline, from audit_evidence.py.

    Four states, phrased for someone deciding whether to act rather than for us:
      verified      we opened the cited page and the deadline is on it
      contradicted  that page says something different - check before acting
      no_quote      the page loaded but does not carry the deadline
      unreadable    we could not open the page

    Only the first two are statements about the DEADLINE. The last two are statements about
    OUR ability to confirm it - the date may well be right, and the row is not downgraded.
    """
    if not path:
        return {}
    out = {}
    with open(path, encoding='utf-8-sig', newline='') as h:
        for r in csv.DictReader(h):
            eid = (r.get('EVENT_ID') or '').strip()
            if eid:
                out[eid] = {'v': (r.get('CHECK') or '').strip(),
                            'u': (r.get('CHECK_URL') or '').strip(),
                            'q': (r.get('CHECK_QUOTE') or '').strip()}
    return out


def build(rows, today='2026-08-07', dead_links=frozenset(), checks=None, recon=None):
    st = edition_states(rows, today)
    _today = date.fromisoformat(today) if isinstance(today, str) else today
    out = []
    corrected = 0
    for r in rows:
        d = {k: (r.get(k) or '').strip() for k in FIELDS}
        # STATUS is upstream's field and we have never written it - it is neither OWNED nor
        # PROTECTED in refresh_delivery. So we do not EDIT it; we DERIVE what to display, which
        # is what the 2026-08-07 backend design said all along ("conference status stays
        # DERIVED"). Writing nine corrected cells into a stored field would be undone by the
        # next delivery; deriving is permanent and cannot regress.
        #
        # It only replaces the stored value where the derivation is BETTER INFORMED - a dated
        # deadline, or an event that has already run while the file still says Open. Reasoning
        # from a blank deadline, or choosing between two true words, leaves the file alone.
        # On 2026-08-31 that was 9 rows of 126 disagreements.
        a = lifecycle.assess(r, st.get((r.get('EVENT_ID') or '').strip(), 'Active'), _today)
        use, _why = a.overrides(d['STATUS'])
        if use:
            d['STATUS'] = a.customer_status
            corrected += 1
        d['Market'] = MARKET_LABEL.get(d['Market'], d['Market'])
        loc = ', '.join(x for x in (d['CITY'], d['STATE_PROVINCE'], d['COUNTRY']) if x)
        conf = d['GROUNDING_CONFIDENCE'].split(' (')[0] or ''
        out.append({
            'n': d['CONFERENCE'], 'm': d['Market'], 'loc': loc, 'f': d['FORMAT'],
            'dates': d['CONFERENCE DATES'], 'start': d['START DATE'],
            'dl': d['SUBMISSION DEADLINE'], 's': d['STATUS'], 'c': conf,
            'proj': d['IS_PROJECTED'] == 'true',
            'det': d['STATUS DETAILS'], 'q': d['DEADLINE_QUOTE'],
            # R16 evidence. Until 2026-09-01 this page read NEITHER field, so a discontinuation -
            # the claim a customer most needs to believe, because it removes a conference from
            # their list - arrived as bare prose while the organiser's own sentence sat unused in
            # the delivery. ESF MENA is the case that found it: the row carries europetro.com's
            # "we have taken the decision not to hold ESF MENA as a standalone event in 2026",
            # and the customer, holding an ACCEPTANCE to it and a $12,500 sponsorship decision,
            # could not see it. An amendment was spent making upstream evidence these claims.
            'lq': d['LIFECYCLE_QUOTE'], 'lev': d['LIFECYCLE_EVIDENCE_URL'],
            # Where our record and the customer's sheet disagree. Keyed on the delivery's own
            # EVENT_ID because the CALLER has already crossed the id boundary through
            # identity.to_canonical - this is a plain lookup, and deliberately so. Every time
            # that translation has been done at the point of use instead, it has been done
            # wrong (contract 5.4, JUDGEMENT rule 17).
            'rec': (recon or {}).get((r.get('EVENT_ID') or '').strip(), []),
            'url': d['CONFERENCE URL'] or d['MAIN_INFO_URL'],
            'sub': d['CFP_SUBMISSION_URL'] or d['SUBMISSION URL'],
            'ev': d['DEADLINE_EVIDENCE_URL'],
            'trk': d['TRACK'], 'op': d['OPPORTUNITY_TYPE'],
            'org': d['ORGANIZER'],
            # v1.5. ONLY 'Yes' becomes a badge. 'Unknown' is the default on every row
            # until someone looks, so rendering it would put a meaningless label on
            # nearly the whole list; and 'No' is the norm, so it is not news either.
            'spon': d['SPONSOR_REQUIRED'].strip().lower() == 'yes',
            'sponcost': d['SPONSOR_COST'], 'sponurl': d['SPONSOR_URL'],
            'sponq': d['SPONSOR_QUOTE'],
            'st': st.get((r.get('EVENT_ID') or '').strip(), 'Active'),
            # When WE last inspected this row at source. Drives the 'Updated since' view -
            # the answer to 'what has moved since I last looked', which is the question a
            # weekly reader actually has.
            'asof': d['SOURCE_AS_OF'],
            # Flag the link the PAGE actually offers, which prefers CFP_SUBMISSION_URL - not
            # whichever column happened to be tested.
            # The truthiness guard is load-bearing: '' in dead_links is True, so one blank line
            # in a dead-links file would flag every row that has no submission URL at all as
            # "Submit Link Missing". A blank is not a broken link.
            'dead': bool((d['CFP_SUBMISSION_URL'] or d['SUBMISSION URL']) and
                         (d['CFP_SUBMISSION_URL'] or d['SUBMISSION URL']) in dead_links),
            # The evidence link needs its OWN flag, checked in ADDITION to the host check in
            # clickable(). A dead host means the event's web presence is gone; a dead page on a
            # live host means the link merely moved, and those need different remedies. Kept
            # separate from `dead` because that drives the "Submit Link Missing" badge, and an
            # evidence problem is not a submission problem.
            # 2026-08-12: without this, Decarb Connect offered "Where the deadline was read" as
            # a working link to a 404 that link_checks had known about for three days.
            'evdead': bool(d['DEADLINE_EVIDENCE_URL'] and
                           d['DEADLINE_EVIDENCE_URL'] in dead_links),
            # ...and the event site itself. Every customer-facing link gets checked, not just
            # the one we happened to sweep. Each keeps its own flag because each carries a
            # different message: the submit page is missing, the evidence page has gone, the
            # event site is down.
            'urldead': bool((d['CONFERENCE URL'] or d['MAIN_INFO_URL']) and
                            (d['CONFERENCE URL'] or d['MAIN_INFO_URL']) in dead_links),
            'chk': (checks or {}).get((r.get('EVENT_ID') or '').strip(), {}).get('v', ''),
            'chku': (checks or {}).get((r.get('EVENT_ID') or '').strip(), {}).get('u', ''),
            'chkq': (checks or {}).get((r.get('EVENT_ID') or '').strip(), {}).get('q', ''),
        })
    if corrected:
        print(f"  {corrected} row(s) shown with a DERIVED status - the file's value was "
              f"contradicted by a date")
    return out


PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conference Review __DATE__</title>
<style>
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#15181d; --muted:#5b6472; --line:#e2e6ec;
  --urgent:#c0392b; --urgentbg:#fdecea; --soon:#9a6200; --soonbg:#fff5e0;
  --open:#136c3c; --openbg:#e6f5ec; --closed:#6b7280; --closedbg:#f0f1f3;
  --accent:#1b4d8f; --accentbg:#e8f0fb; --warnbg:#fdf3e3; --warn:#8a5a00;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1216; --panel:#171b21; --ink:#e8ecf2; --muted:#9aa5b4; --line:#272d36;
  --urgent:#ff8b7d; --urgentbg:#3a1d19; --soon:#ffc14d; --soonbg:#3a2e12;
  --open:#5fd48c; --openbg:#12301f; --closed:#98a2b3; --closedbg:#20252d;
  --accent:#7fb0f0; --accentbg:#16243a; --warnbg:#33270f; --warn:#e8b45f;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:14px 20px;
  position:sticky;top:0;z-index:20}
h1{margin:0 0 2px;font-size:17px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:12px}
.wrap{padding:16px 20px 60px;max-width:1600px;margin:0 auto}
.sec{margin:14px 0}
.sechd{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
  font-weight:700;margin:0 0 7px 2px}
.views{display:flex;gap:8px;flex-wrap:wrap}
.view{flex:1 1 168px;justify-content:flex-start}
.key{display:flex;gap:16px;flex-wrap:wrap;margin-top:11px;padding-top:11px;
  border-top:1px dashed var(--line);font-size:11.5px;color:var(--muted)}
.key span b{color:var(--ink);font-weight:600}
.view{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:8px;
  padding:9px 13px;cursor:pointer;font:inherit;display:flex;gap:8px;align-items:center;
  transition:.12s}
.view:hover{border-color:var(--accent)}
.view.on{background:var(--accent);border-color:var(--accent);color:#fff}
.view .c{font-weight:700;font-variant-numeric:tabular-nums}
.view small{display:block;font-size:11px;color:var(--muted);font-weight:400}
.view.on small{color:rgba(255,255,255,.85)}
.filters{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end}
.sec:last-of-type{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px}
.sec:first-of-type .chips{gap:7px}
.fg{display:flex;flex-direction:column;gap:5px}
.fg label{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  font-weight:600}
select,input[type=search]{font:inherit;padding:7px 9px;border:1px solid var(--line);
  border-radius:7px;background:var(--bg);color:var(--ink);min-width:150px}
input[type=search]{min-width:230px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:20px;
  padding:5px 11px;cursor:pointer;font-size:12px}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
/* Sub-filters appear only for the view they belong to, so the page does not carry
   three extra controls that are meaningless most of the time. */
.subs{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:-4px 0 4px;
  padding:9px 12px;background:var(--accentbg);border-radius:8px}
.subs .lbl{font-size:11px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--muted);margin-right:2px}
.bar{display:flex;justify-content:space-between;align-items:center;margin:12px 0 8px;
  flex-wrap:wrap;gap:10px}
.count{font-size:13px;color:var(--muted)}
.count b{color:var(--ink);font-size:15px}
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);padding:10px;border-bottom:1px solid var(--line);
  background:var(--panel);cursor:pointer;white-space:nowrap}
th:hover{color:var(--accent)}
td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
tr.r{cursor:pointer}
tr.r:hover td{background:var(--accentbg)}
.nm{font-weight:600;max-width:340px}
.mk{font-size:11px;color:var(--muted)}
.b{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600;
  white-space:nowrap}
.b-open{background:var(--openbg);color:var(--open)}
.b-closed{background:var(--closedbg);color:var(--closed)}
.b-up{background:var(--accentbg);color:var(--accent)}
.b-nv{background:var(--warnbg);color:var(--warn)}
.b-dead{background:var(--urgentbg);color:var(--urgent)}
.b-ok{background:var(--openbg);color:var(--open)}
a.chklink{text-decoration:none}
a.chklink:hover .b{outline:2px solid var(--accent);outline-offset:1px}
a.dl-dead{color:var(--urgent);text-decoration:line-through}
.b-urg{background:var(--urgentbg);color:var(--urgent)}
.b-soon{background:var(--soonbg);color:var(--soon)}
.dl{font-variant-numeric:tabular-nums;white-space:nowrap}
.days{font-size:11px;font-weight:700;margin-left:6px}
.proj{font-size:11px;color:var(--warn);border:1px dashed var(--warn);border-radius:4px;
  padding:0 5px;margin-left:6px}
.det{background:var(--bg)}
.det td{padding:14px 16px;font-size:13px}
.det h4{margin:0 0 4px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted)}
.det p{margin:0 0 12px}
.quote{border-left:3px solid var(--accent);padding:4px 0 4px 10px;color:var(--muted);
  font-style:italic}
a{color:var(--accent)}
.links a{display:inline-block;margin-right:14px}
.empty{padding:48px;text-align:center;color:var(--muted)}
.legend{margin-top:22px;padding:14px;background:var(--panel);border:1px solid var(--line);
  border-radius:10px;font-size:12px;color:var(--muted)}
.legend b{color:var(--ink)}
@media print{header{position:static}.views,.filters,.legend{display:none}
  th{position:static}body{background:#fff}}
.cvbox{background:#fff;border:1px solid var(--line);border-left:3px solid var(--ink);
  border-radius:4px;padding:14px 16px;margin:0 0 18px}
.cvbox h2{font-size:15px;margin:0 0 4px;font-weight:700}
.cvbox .lede{font-size:13px;color:var(--muted);margin:0 0 10px;max-width:70ch}
.cvrow{padding:9px 0;border-top:1px solid var(--line)}
.cvrow:first-of-type{border-top:none}
.cvrow .nm{font-weight:600;font-size:13.5px}
.cvrow .ans{font-size:12.5px;color:var(--muted);margin-top:2px;max-width:78ch}
.cvrow .qt{font-size:12px;color:var(--ink);background:#f6f7f9;border-left:2px solid var(--line);
  padding:5px 8px;margin-top:5px;border-radius:0 3px 3px 0;max-width:78ch}
.cvst{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;padding:2px 6px;border-radius:3px;margin-left:6px;vertical-align:1px}
.s-confirmed{background:#e4efe8;color:#2c6a4d}
.s-held{background:#f7eeda;color:#8f6317}
.s-none{background:#eef0f3;color:#5b636d}
.s-ask{background:#e3edf5;color:#2a5b87}
</style></head><body>
<header>
  <h1>Conference &amp; Call-for-Papers Review</h1>
  <div class="sub">__COUNT__ conferences &middot; __SCOPE__ &middot; data as at __DATE__ &middot;
    urgency recalculated live against today's date</div>
</header>
<div class="wrap">

  <section class="sec">
    <div class="sechd">Market</div>
    <div class="chips" id="mk"></div>
  </section>

  <section class="sec">
    <div class="sechd">Timing</div>
    <div class="views" id="views"></div>
    <div class="subs" id="subs" style="display:none"></div>
  </section>

  <section class="sec">
    <div class="sechd">Refine</div>
    <div class="filters">
    <div class="fg"><label>Search</label>
      <input type="search" id="q" placeholder="Conference, city, track..."></div>
    <div class="fg"><label>Status</label><select id="fs">
      <option value="">All statuses</option><option>Open</option><option>Upcoming</option>
      <option>Closed</option><option>Needs Verification</option></select></div>
    <div class="fg"><label>Format</label><select id="ff">
      <option value="">Any format</option><option>In-Person</option><option>Hybrid</option>
      <option>Virtual</option></select></div>
    <div class="fg"><label>Edition</label><select id="fe">
      <option value="">Any edition state</option><option>Active</option>
      <option>Watching</option><option>Archived</option><option>Discontinued</option></select></div>
    <div class="fg"><label>Confidence</label><select id="fc">
      <option value="">Any confidence</option><option value="Confirmed">Confirmed</option>
      <option value="Disputed">Disputed</option>
      <option value="NotOnPage">Not on page</option>
      <option value="NoCheck">Could not check</option></select></div>
      <div class="fg"><label>Updated since</label>
        <input type="date" id="fsince" value="__SINCE__"></div>
    </div>
    <div class="key" id="key"></div>
  </section>

  <div class="bar">
    <div class="count"><b id="n">0</b> shown <span id="ctx"></span></div>
    <div class="count" id="hint"></div>
  </div>

  <table id="t"><thead><tr>
    <th data-k="n">Conference</th><th data-k="m">Market</th><th data-k="loc">Location</th>
    <th data-k="f">Format</th><th data-k="start">Event dates</th>
    <th data-k="dl">CFP deadline</th><th data-k="s">Status</th>
    <th data-k="st">Edition</th><th data-k="c">Confidence</th>
  </tr></thead><tbody id="tb"></tbody></table>
  <div class="empty" id="none" style="display:none">Nothing matches those filters.</div>

  <div class="legend">
    <b>Confirmed</b> means we opened the page the research cites and read the deadline there.
    Everything else splits three ways, because they need different things from you.
    <b>Disputed</b> - that page states a different date; decide which is right, and start here.
    <b>Not on page</b> - the page opened but never mentions this deadline, so the date may be
    right yet nothing backs it. <b>Could not check</b> - the page would not load <i>for us</i>;
    needs manual verification, so treat it as unchecked rather than doubtful.
    &nbsp;&middot;&nbsp;
    <b>Submit Link Missing</b> means the submission page is not found when a real browser opens it, so
    do not send a client there. The conference itself may be perfectly healthy &mdash; organisers
    move these pages between editions. Use <i>Submit Link Missing</i> above to see them all.
    &nbsp;&middot;&nbsp;
    <b>Edition</b> describes the LIFECYCLE, not the date. <b>Discontinued</b> means the
    conference has ceased to exist &mdash; a row labelled 2027 can still be discontinued,
    because the year in its name was an assumption, not a fact.
    &nbsp;&middot;&nbsp;
    <b>Verified dates</b> means the event dates are confirmed but the organiser has not
    announced a speaking deadline yet - normal for events 6-12 months out, and not a gap in
    our research.
    &nbsp;&middot;&nbsp;
    <b>Confidence</b> &mdash; <b>Verified</b> means the deadline was read on the event's own
    page and the exact sentence is recorded. <b>Projected</b> means it is an informed estimate
    with nothing on the page confirming it &mdash; check before sending a client.
    &nbsp;&middot;&nbsp; <b>Needs Verification</b> rows could not be researched automatically
    and carry no invented data. &nbsp;&middot;&nbsp; Click any row for the full detail,
    the quoted evidence and the submission link.
  </div>
</div>

<script>
const DATA = __DATA__;
const DEAD_HOSTS = __DEADHOSTS__;
const today = new Date(); today.setHours(0,0,0,0);
const URGENT_DAYS = __URGENT_DAYS__, SOON_DAYS = __SOON_DAYS__;
// Mutable: the date box rewrites it and every count recomputes. Declared with `let` on
// purpose - a const here would make the box decorative.
let SINCE = '__SINCE__';
const days = s => { if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(s||'')) return null;
  const p=s.split('-'); const d=new Date(+p[0],+p[1]-1,+p[2]); d.setHours(0,0,0,0);
  return Math.round((d-today)/864e5); };
DATA.forEach(r=>{ r.dd = days(r.dl); r.sd = days(r.start);
  // A STORED STATUS GOES STALE THE DAY AFTER IT IS WRITTEN. STATUS comes from the delivery and
  // was right when produced; the date then passes and nothing updates it. On 2026-08-11 eight
  // rows read "Open" with a deadline already gone, four of them within the previous week - and
  // the page showed "passed" in the deadline column beside an Open badge on the same line.
  // Derive it here instead, from the reader's today, so a page opened next month is still
  // right. Contract 2.2: derive, do not mutate.
  if(r.dd!==null && r.dd<0 && (r.s==='Open'||r.s==='Upcoming')){ r.s='Closed'; r.sderived=1; }
});

const VIEWS = [
 {k:'urgent', t:'Closing this week', d:URGENT_DAYS+' days or less',
  f:r=>r.dd!==null&&r.dd>=0&&r.dd<=URGENT_DAYS},
 {k:'soon', t:'Closing this month', d:SOON_DAYS+' days or less',
  f:r=>r.dd!==null&&r.dd>=0&&r.dd<=SOON_DAYS},
 {k:'openevent', t:'Event soon, open', d:'event within 4 months',
  f:r=>r.s==='Open'&&r.sd!==null&&r.sd>=0&&r.sd<=120},
 {k:'open', t:'All open calls', d:'accepting now', f:r=>r.s==='Open'},
 {k:'watching', t:'Awaiting next', d:'hunting next date', f:r=>r.st==='Watching'},
 // WHAT HAS MOVED SINCE I LAST LOOKED. The question a weekly reader actually has, and until
 // now the page could not answer it - every view described the CURRENT state and none
 // described a CHANGE. `asof` is the date we last inspected the row at source, so this is
 // "rows we have been back to", which is the honest version: we cannot claim the conference
 // changed, only that we checked it again and this is what it says now.
 {k:'recent', t:'Updated since', d:'we re-checked these', f:r=>r.asof && r.asof >= SINCE},
 {k:'checked', t:'Deadline confirmed', d:'we read it on their page', f:r=>r.chk==='verified'},
 // "we could not confirm" put the doubt on us and left the reader guessing what to do about
 // it. "the cited page doesn't back the date" says what is actually true and points at the
 // thing to check. The date may well be right - most of this bucket is a page that loaded
 // fine and simply does not mention the deadline.
 {k:'unconfirmed', t:'Need to Verify', d:"cited page doesn't back the date", f:r=>r.chk==='contradicted'||r.chk==='no_quote'||r.chk==='unreadable'},
 {k:'broken', t:'Submit Link Missing', d:'the page is not found', f:r=>r.dead},
 {k:'reconcile', t:'Check against your sheet', d:'our record and yours differ',
  f:r=>r.rec && r.rec.length},
 {k:'all', t:'Everything', d:'full list', f:r=>true},
];
// "Closing this month" is the right landing view when something IS closing this month. On a
// per-client page it often is not - Arnica had none - and the page then opened on "Nothing
// matches those filters", which reads as a broken product rather than a quiet month.
// So: land on the intended view when it has rows, otherwise the first view that does, and
// "Everything" as the floor. A page must never open empty.
let view='soon';
let sortK='dl', sortDir=1;
const mkts=[...new Set(DATA.map(r=>r.m))].sort(); const active=new Set();
const $=i=>document.getElementById(i);

// COUNTS FOLLOW THE MARKET FILTER. They used to be written once at load from the whole
// database, so picking Utility left "Need to Verify 81" on screen while the table below showed
// four rows. The customer spotted it immediately, and it matters because his daily instruction
// to his team is "get Need to Verify to zero" - which is unusable if the number is not the one
// in front of them.
const inMkt = r => !active.size || active.has(r.m);

// Correct the landing view now that inMkt exists, and count THROUGH it for the same reason the
// chips do. "Closing this month" is right when something is closing this month; on a
// per-client page it often is not - Arnica had none - and the page then opened on "Nothing
// matches those filters", which reads as a broken product rather than a quiet month.
// Everything is the floor: a page must never open empty.
for (const k of ['soon','urgent','open','recent','watching','all']) {
  const v = VIEWS.find(x=>x.k===k);
  if (v && DATA.filter(r=>inMkt(r)&&v.f(r)).length) { view = k; break; }
  if (k === 'all') view = 'all';
}
function drawViews(){
  $('views').innerHTML = VIEWS.map(v=>
   `<button class="view${v.k===view?' on':''}" data-v="${v.k}">
     <span class="c">${DATA.filter(r=>inMkt(r)&&v.f(r)).length}</span>
     <span>${v.t}<small>${v.d}</small></span></button>`).join('');
}
drawViews();
$('mk').innerHTML = mkts.map(m=>
  `<button class="chip" data-m="${m}">${m} <span style="opacity:.6">${
    DATA.filter(r=>r.m===m).length}</span></button>`).join('');
$('key').innerHTML = [
 ['Active','tracking this edition now'],
 ['Awaiting next','this edition has run; hunting the next date'],
 ['Archived','a newer edition exists; this one is final'],
 ['Discontinued','the conference no longer exists'],
].map(([k,v])=>`<span><b>${k}</b> &mdash; ${v}</span>`).join('')
 + '<span><b>Confirmed</b> &mdash; we opened the cited page and read the deadline there</span>'
 + '<span><b>Disputed</b> &mdash; the cited page states a different date; decide which is right</span>'
 + '<span><b>Not on page</b> &mdash; the page opened but does not mention this deadline</span>'
 + '<span><b>Could not check</b> &mdash; the page would not load for us; needs manual verification</span>'
 + '<span><b>Verified dates</b> &mdash; event dates confirmed; deadline not announced yet</span>'
 + '<span><b>Projected</b> &mdash; estimate, nothing on the page confirms it</span>';

const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// Is this a link we should actually OFFER the customer?
// A stored URL was right when it was stored; the domain can lapse afterwards and then every
// click on it fails. "Page we checked" is the common case - it records what the audit read on
// the day, and three rows were still offering sffsymposium.engr.utexas.edu and
// spemedicalplastics.org weeks after both went NXDOMAIN.
// ONE DEFINITION, EVERY CALL SITE. The first version of this guarded only the badge in
// chkCell and missed the identical link in the detail panel, so a dead link kept rendering
// while the check reported success.
function clickable(u){
  if(!u) return false;
  if(!DEAD_HOSTS.length) return true;
  try{ return !DEAD_HOSTS.includes(new URL(u).hostname.toLowerCase()); }
  catch(e){ return true; }
}
const CHK={verified:['b-open','Confirmed','We opened the page they cite and read the deadline on it'],
           contradicted:['b-dead','Disputed','The cited page states a different deadline'],
           no_quote:['b-nv','Not on page','The cited page opened fine but does not mention this deadline. The date may still be right - the source does not back it.'],
           unreadable:['b-nv','Could not check','The page would not load for us; needs manual verification.']};
function chkCell(r){
  const [cls,txt,tip]=CHK[r.chk];
  const badge=`<span class="b ${cls}">${txt}</span>`;
  // No page to open (rare) - leave it as a plain badge rather than a dead link.
  if(!r.chku) return `<span title="${esc(tip)}">${badge}</span>`;
  // Nor when the host has since stopped existing - see clickable().
  if(!clickable(r.chku))
    return `<span title="${esc(tip)} - the page we checked is no longer online">${badge}</span>`;
  return `<a class="chklink" href="${esc(r.chku)}" target="_blank" rel="noopener"
     title="${esc(tip)} - opens the page we checked" onclick="event.stopPropagation()">${badge}</a>`;
}

function dlCell(r){
  if(!r.dl) return '<span style="color:var(--muted)">not announced</span>';
  let b='';
  if(r.dd!==null&&r.dd>=0&&r.dd<=URGENT_DAYS) b=`<span class="days b b-urg">${r.dd}d left</span>`;
  else if(r.dd!==null&&r.dd>=0&&r.dd<=SOON_DAYS) b=`<span class="days b b-soon">${r.dd}d left</span>`;
  else if(r.dd!==null&&r.dd<0) b=`<span class="days" style="color:var(--muted)">passed</span>`;
  return `<span class="dl">${r.dl}${b}</span>`;
}
const sB={'Open':'b-open','Closed':'b-closed','Upcoming':'b-up','Needs Verification':'b-nv'};
const eB={'Active':'b-open','Watching':'b-soon','Archived':'b-closed','Discontinued':'b-nv'};

const SUBS=[['Disputed','Disputed',r=>r.chk==='contradicted'],
           ['NotOnPage','Not on page',r=>r.chk==='no_quote'],
           ['NoCheck','Could not check',r=>r.chk==='unreadable']];

function drawSubs(){
  const box=$('subs');
  if(view!=='unconfirmed'){ box.style.display='none'; return; }
  const base=DATA.filter(r=>inMkt(r)&&VIEWS.find(v=>v.k===view).f(r));
  const cur=$('fc').value;
  box.style.display='flex';
  box.innerHTML='<span class="lbl">Which kind</span>'
    + `<button class="chip${cur===''?' on':''}" data-s="">All ${base.length}</button>`
    + SUBS.map(([k,t,f])=>`<button class="chip${cur===k?' on':''}" data-s="${k}">${t} ${
        base.filter(f).length}</button>`).join('');
}

function render(){
  const q=$('q').value.toLowerCase(), fs=$('fs').value, ff=$('ff').value,
        fc=$('fc').value, fe=$('fe').value;
  const vf=VIEWS.find(v=>v.k===view).f;
  let rows=DATA.filter(r=>vf(r)
    && (!fs||r.s===fs) && (!ff||r.f===ff) && (!fe||r.st===fe)
    && (!fc || (fc==='Confirmed' ? r.chk==='verified'
             :  fc==='Disputed'  ? r.chk==='contradicted'
             :  fc==='NotOnPage' ? r.chk==='no_quote'
             :  fc==='NoCheck'   ? r.chk==='unreadable'
             :  true))
    && (!active.size||active.has(r.m))
    && (!q||(r.n+' '+r.loc+' '+r.trk+' '+r.m).toLowerCase().includes(q)));
  rows.sort((a,b)=>{
    let x=a[sortK]??'', y=b[sortK]??'';
    if(sortK==='dl'){ // undated last, then soonest first
      const ax=a.dd===null?1e9:(a.dd<0?1e8-a.dd:a.dd), by=b.dd===null?1e9:(b.dd<0?1e8-b.dd:b.dd);
      return (ax-by)*sortDir; }
    return String(x).localeCompare(String(y))*sortDir;
  });
  $('n').textContent=rows.length;
  $('ctx').textContent = view==='all'?'':'in "'+VIEWS.find(v=>v.k===view).t.toLowerCase()+'"';
  const urg=rows.filter(r=>r.dd!==null&&r.dd>=0&&r.dd<=URGENT_DAYS).length;
  $('hint').innerHTML = urg?`<span class="b b-urg">${urg} closing within ${URGENT_DAYS} days</span>`:'';
  $('tb').innerHTML = rows.map((r,i)=>`
   <tr class="r" data-i="${i}">
    <td class="nm">${esc(r.n)}${r.op&&r.op!=='Speaking'?` <span class="b b-up">${r.op}</span>`:''}${
      // SPONSOR REQUIRED IS A GATE ON THE OPPORTUNITY, NOT A DETAIL. It decides whether the
      // pitch happens at all, so it belongs in the list where a deadline is - not three
      // clicks down. The cost rides with it when we have one, because "sponsor required" and
      // "sponsor required, $25,000" are different decisions.
      r.spon?` <span class="b b-nv" title="Speaking at this event requires sponsorship. Open the row for the source.">Sponsor required${r.sponcost?' &middot; '+esc(r.sponcost):''}</span>`:''}${
      r.dead?' <span class="b b-dead" title="The submission page returns not-found - confirmed in a real browser">Submit Link Missing</span>':''}</td>
    <td class="mk">${esc(r.m)}</td><td class="mk">${esc(r.loc)||'&mdash;'}</td>
    <td class="mk">${esc(r.f)||'&mdash;'}</td><td class="mk">${esc(r.dates)||'&mdash;'}</td>
    <td>${dlCell(r)}</td>
    <td><span class="b ${sB[r.s]||''}"${r.sderived?' title="The deadline has passed. Shown as closed based on the date, whatever the source last said."':''}>${esc(r.s)}</span></td>
    <td><span class="b ${eB[r.st]||''}">${esc(r.st)}</span></td>
    <td>${
      r.chk ? chkCell(r) :
      // PROJECTED OVERRIDES A STORED "Verified". GROUNDING_CONFIDENCE is upstream's and was
      // written when the row had a citation; withdrawing that citation sets IS_PROJECTED
      // without touching it, so seven rows showed a green "Verified" badge on a date nothing
      // backs any more. Same failure as STATUS going stale - the honest value is derivable,
      // so derive it rather than trusting what was stored.
      (r.c==='Verified' && !r.proj) ? (r.dl ? '<span class="b b-open">Verified</span>'
                                            : '<span class="b b-open">Verified dates</span>') :
      r.c                   ? '<span class="b b-nv">Projected</span>' : '&mdash;'}</td>
   </tr>
   <tr class="det" id="d${i}" style="display:none"><td colspan="9">
     ${r.det?`<h4>Status</h4><p>${esc(r.det)}</p>`:''}
     ${r.q?(r.ev
        ? `<h4>Quoted from the source page</h4><p class="quote">${esc(r.q)}</p>`
        // No source URL means the heading would be a claim we cannot support. Three rows carry
        // research notes rather than page quotes - "the call has not yet been announced" and
        // similar. Useful to read, wrong to present as something we read off a page, and it is
        // exactly the standard we hold upstream to.
        : `<h4>Research note <span style="font-weight:400;color:var(--muted)">&mdash; no source page recorded</span></h4><p class="quote">${esc(r.q)}</p>`):''}
     ${r.rec&&r.rec.length?`<h4>Check against your sheet</h4>${r.rec.map(x=>
        `<p><b>${esc(x.cat)}</b>${x.acted?' <span style="color:var(--muted)">&mdash; you have already actioned this row</span>':''}<br>
         ${esc(x.detail)}<br>
         <span style="color:var(--muted)">your sheet:</span> ${esc(x.theirs)||'&mdash;'}
         ${x.ours?`<br><span style="color:var(--muted)">our record:</span> ${esc(x.ours)}`:''}
         ${x.ours_wrong?'<br><b>Ours looks like the wrong one here</b> &mdash; we will correct it.':''}</p>`).join('')}`:''}
     ${r.lq?`<h4>Why this is no longer running${r.lev?` &mdash; <a href="${esc(r.lev)}" target="_blank" rel="noopener">from the organiser</a>`:' <span style="font-weight:400;color:var(--muted)">&mdash; no source page recorded</span>'}</h4><p class="quote">${esc(r.lq)}</p>`:''}
     ${r.chkq?`<h4>What we found when we checked</h4><p class="quote">${esc(r.chkq)}</p>`:''}
     ${r.spon?`<h4>Sponsorship</h4><p>${r.sponcost?'<b>'+esc(r.sponcost)+'</b> &mdash; ':''}speaking at this event requires sponsorship.</p>${
        r.sponq?`<p class="quote">${esc(r.sponq)}</p>`
               :`<p style="color:var(--muted)">We have not yet read a sentence on their page confirming this. Treat the figure as unverified until we have.</p>`}`:''}
     ${r.org?`<h4>Organized by</h4><p>${esc(r.org)}</p>`:''}
     ${r.trk?`<h4>Tracks</h4><p>${esc(r.trk)}</p>`:''}
     <div class="links">
       ${clickable(r.url)?(r.urldead
          ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="dl-dead">Event site (not found)</a>`
          : `<a href="${esc(r.url)}" target="_blank" rel="noopener">Event site</a>`):''}
       ${(r.sub&&clickable(r.sub))?(r.dead
          ? `<a href="${esc(r.sub)}" target="_blank" rel="noopener" class="dl-dead">Submit page (missing)</a>`
          : `<a href="${esc(r.sub)}" target="_blank" rel="noopener">Submit here</a>`):''}
       ${clickable(r.ev)?(r.evdead
          ? `<a href="${esc(r.ev)}" target="_blank" rel="noopener" class="dl-dead">Where the deadline was read (page gone)</a>`
          : `<a href="${esc(r.ev)}" target="_blank" rel="noopener">Where the deadline was read</a>`):''}
       ${clickable(r.chku)?`<a href="${esc(r.chku)}" target="_blank" rel="noopener">Page we checked</a>`:''}
       ${(r.spon&&clickable(r.sponurl))?`<a href="${esc(r.sponurl)}" target="_blank" rel="noopener">Sponsorship page</a>`:''}
     </div></td></tr>`).join('');
  drawViews();
  drawSubs();
  $('none').style.display=rows.length?'none':'block';
  document.querySelectorAll('tr.r').forEach(tr=>tr.onclick=()=>{
    const d=$('d'+tr.dataset.i); d.style.display=d.style.display==='none'?'table-row':'none';});
}
$('views').onclick=e=>{const b=e.target.closest('[data-v]'); if(!b)return;
  view=b.dataset.v; document.querySelectorAll('.view').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  if(SUBS.some(([k])=>k===$('fc').value)) $('fc').value='';
  render();};
$('subs').onclick=e=>{const b=e.target.closest('[data-s]'); if(!b)return;
  $('fc').value=b.dataset.s; render();};
$('mk').onclick=e=>{const b=e.target.closest('[data-m]'); if(!b)return;
  const m=b.dataset.m; active.has(m)?active.delete(m):active.add(m);
  b.classList.toggle('on'); render();};
['q','fs','ff','fc','fe'].forEach(i=>$(i).oninput=render);
// The date box drives SINCE, so the "Updated since" count changes with it rather than being
// fixed at build time. Falls back to the built-in default when cleared - an empty box would
// otherwise make every row match and the view would silently become "everything".
$('fsince').oninput=()=>{ SINCE = $('fsince').value || '__SINCE__'; render(); };
document.querySelectorAll('th').forEach(th=>th.onclick=()=>{
  const k=th.dataset.k; sortDir = (k===sortK)? -sortDir : 1; sortK=k; render();});
render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-i', '--input', required=True)
    ap.add_argument('-o', '--output', required=True)
    ap.add_argument('--date', default='2026-08-07')
    ap.add_argument('--db', help='PREFERRED source for dead links: read link_checks directly, '
                                 'so the picture cannot be stale. Supplying this satisfies '
                                 '--dead-links.')
    ap.add_argument('--dead-links', help='URLs a browser confirmed dead; adds the Submit-Link-Missing flag')
    ap.add_argument('--checks', help='deadline verification CSV from audit_evidence.py')
    ap.add_argument('--dead-hosts', help='hosts that no longer resolve, one per line, from '
                                         'scripts/check_dns.py. Links to these are withheld '
                                         'rather than offered to the customer.')
    ap.add_argument('--markets', default='',
                    help='comma-separated markets to include, e.g. Cybersecurity,Utility. '
                         'The market CHIPS still work inside whatever is included - this sets '
                         'what the page is ABOUT, the chips filter within it.')
    ap.add_argument('--client', help='client key (e.g. arnica). Scopes to one client\'s '
                                     'conferences. Kept for the platform, where isolation is '
                                     'per client; for a page, --markets is usually what you '
                                     'want.')
    ap.add_argument('--client-since', default='',
                    help='ISO date the "Updated since" view starts from; defaults to a week '
                         'back. The reader can move it on the page.')
    ap.add_argument('--reconcile', action='store_true',
                    help='compare our record against the customer sheets in the database and '
                         'add the "Check against your sheet" view. Needs --db.')
    ap.add_argument('--no-evidence', action='store_true',
                    help='build WITHOUT dead-links/checks. Layout testing only - the resulting '
                         'page understates the work and must never be sent.')
    a = ap.parse_args()

    # A MISSING INPUT MUST NOT READ AS A FINDING. Both flags are optional and default to empty,
    # so omitting them produces a complete-looking page with "Deadline confirmed 0",
    # "Need to Verify 0" and "Submit Link Missing 0". That is not a blank page a reader would
    # question - it is a confident claim that nothing was verified and nothing is broken, which
    # is the opposite of the truth (74, 96 and 41 on the 2026-08-07 delivery). Caught 2026-08-11
    # when a page built for a layout test was read as though the numbers meant something.
    if not a.no_evidence and not ((a.dead_links or a.db) and a.checks):
        missing = [f for f, v in (('--db or --dead-links', a.dead_links or a.db),
                                  ('--checks', a.checks)) if not v]
        ap.error(
            f"refusing to build: {' and '.join(missing)} not supplied.\n"
            "  Those flags populate Deadline confirmed / Need to Verify / Submit Link Missing.\n"
            "  Without them the page shows 0 for each, which reads as a result rather than an\n"
            "  omission. Pass both, or --no-evidence if you are only checking layout.")

    # A STALE EXPORT IS WORSE THAN NO EXPORT, because it looks like an answer. On 2026-08-12
    # this page was built from an Aug-8 dead-link export while the database had known since
    # Aug-9 that a cited page was dead, and it shipped as a working link on a row labelled
    # Verified. If the database is available it wins outright; if the operator insists on a
    # file, it must not predate the newest check.
    if a.db and a.dead_links:
        print('--db supplied: reading link_checks directly and IGNORING --dead-links '
              '(a file cannot go stale if it is not read).')
    elif a.dead_links and a.db is None:
        print('note: --dead-links is a point-in-time export. Prefer --db so it cannot go stale.')

    with open(a.input, encoding='utf-8-sig', newline='') as h:
        rows = list(csv.DictReader(h))

    # MARKET SCOPE. Which markets the page is ABOUT. The chips still filter within it, so a
    # two-market page keeps both chips and a reader can still narrow to one - the scope decides
    # what exists, the chips decide what is shown.
    scope_label = '8 markets'
    if a.markets:
        want = {m.strip() for m in a.markets.split(',') if m.strip()}
        unknown = want - set(MARKET_LABEL) - set(MARKET_LABEL.values())
        if unknown:
            raise SystemExit(f'ERROR: unknown market(s) {sorted(unknown)}. '
                             f'Known: {sorted(set(MARKET_LABEL.values()))}')
        before = len(rows)
        rows = [r for r in rows if (r.get('Market') or '').strip() in want
                or MARKET_LABEL.get((r.get('Market') or '').strip()) in want]
        if not rows:
            raise SystemExit(f'ERROR: {sorted(want)} matched NO rows of {before}. That is a '
                             f'naming mismatch, not an empty market.')
        scope_label = ' + '.join(sorted(MARKET_LABEL.get(m, m) for m in want))
        print(f'scoped to {scope_label}: {len(rows)} of {before} row(s)')

    # SCOPE FIRST, before anything is computed. A client sees only their own conferences, and
    # filtering after the fact would leave the counts, the urgency banner and the market chips
    # all describing rows this client cannot see. Two clients in one industry must never see
    # each other exist (backend design, 2026-08-07, section 10a).
    client_ctx = None
    if a.client:
        if not a.db:
            raise SystemExit('ERROR: --client needs --db - the client layer lives there.')
        con = sqlite3.connect(a.db)
        con.row_factory = sqlite3.Row
        cl = con.execute('select name, industry from clients where client_key = ?',
                         (a.client,)).fetchone()
        if not cl:
            raise SystemExit(f'ERROR: no client {a.client!r} in the database.')
        theirs = {r[0] for r in con.execute(
            'select event_id from client_conferences where client_key = ? '
            'and event_id is not null and trim(event_id) != "" '
            'and withdrawn_by_customer = 0', (a.client,))}
        # Their EVENT_IDs are OURS (the client layer stores canonical ids); the delivery's are
        # upstream's. Translate, or every row fails to match and the page silently comes out
        # empty - which looks exactly like a client who tracks nothing.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import scripts.apply_resolutions as _ar

        class _S:
            path = a.db
        up_to_canon, _roots = _ar._seed_map(_S())
        before = len(rows)
        rows = [r for r in rows
                if up_to_canon.get((r.get('EVENT_ID') or '').strip(),
                                   (r.get('EVENT_ID') or '').strip()) in theirs]
        if not rows:
            raise SystemExit(
                f'ERROR: scoping to {a.client!r} left NO rows of {before}. That is a join '
                f'failure, not a client who tracks nothing - check the EVENT_ID map.')
        # DEFAULT FOR THE "UPDATED SINCE" VIEW. A week, because that is the rhythm the customer
        # reads on. It is only a default - the date box on the page moves it, and the count
        # recomputes in the browser.
        since = a.client_since or (date.fromisoformat(a.date) - timedelta(days=7)).isoformat()
        client_ctx = {'key': a.client, 'name': cl['name'], 'industry': cl['industry'],
                      'since': since}
        con.close()
        print(f"scoped to {cl['name']}: {len(rows)} of {before} row(s); "
              f"'updated since' defaults to {since}")

    dead = load_dead_links(None if a.db else a.dead_links, a.db)
    checks = load_checks(a.checks)
    # Hosts that no longer resolve (scripts/check_dns.py). Distinct from dead_links, which is
    # about a PAGE returning nothing useful; this is about the domain having gone away, so any
    # link to it is unclickable no matter which page it points at.
    dead_hosts = []
    if a.dead_hosts and os.path.exists(a.dead_hosts):
        with open(a.dead_hosts, encoding='utf-8') as h:
            dead_hosts = [ln.strip().lower() for ln in h if ln.strip()]
        print(f'{len(dead_hosts)} host(s) that no longer resolve - links to them withheld')
    # ---- reconcile against the customer's own sheets ------------------------------------
    # The id crossing happens HERE, once, through identity - not inside build(). Contract 5.4:
    # the delivery carries UPSTREAM's EVENT_ID, the client layer carries OURS.
    #
    # THE VIEW IS CALLED "Check against your sheet", NOT "sheet errors". Each item is a
    # disagreement between two records, and on the data this was first built against we are the
    # wrong side twice - a 2025 deadline where their sheet holds 2026, and a passed date for
    # Troopers where they hold 2027. A customer handed a list of their own mistakes, most of
    # which are not theirs, stops reading it. `ours_wrong` says so on the row itself.
    #
    # THIS RATIONALE LIVES IN PYTHON, NOT IN THE JS TEMPLATE. The first version put it in a
    # `//` comment inside the view list, which shipped it into the customer-facing HTML - so
    # anyone opening view-source read our internal reasoning about which rows we had got wrong.
    # Python comments do not reach the page; template comments do.
    recon = {}
    if a.reconcile:
        if not a.db:
            raise SystemExit('ERROR: --reconcile needs --db - the client layer lives there.')
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.cfp_monitor import identity, sheet_reconcile   # noqa: PLC0415

        up_to_canon, roots = identity.seed_map(a.db)
        # A path fault produces an empty map, every row falls through untranslated, and the
        # result is zero findings - indistinguishable from two records that agree.
        identity.assert_mapped(up_to_canon, roots)
        by_canon = identity.index_by_canonical(rows, up_to_canon)
        con = sqlite3.connect(a.db)
        con.row_factory = sqlite3.Row
        client_rows = [dict(x) for x in con.execute('select * from client_conferences')]
        items = sheet_reconcile.reconcile(client_rows, by_canon, date.fromisoformat(a.date))
        n_cov = 0
        for it in items:
            row = by_canon.get(it['eid']) if it['eid'] else None
            if it['kind'] == 'coverage' or row is None:
                n_cov += 1
                continue
            recon.setdefault((row.get('EVENT_ID') or '').strip(), []).append(it)
        n_conf = sum(len(v) for v in recon.values())
        print(f'reconciled against {len(client_rows)} customer row(s): {n_conf} disagreement(s) '
              f'on {len(recon)} row(s); {n_cov} of their rows not joined to ours')

    data = build(rows, a.date, dead, checks, recon)
    n_dead = sum(1 for d in data if d['dead'])
    n_chk = sum(1 for d in data if d['chk'] == 'verified')
    print('{} row(s); {} dead link(s); {} deadline(s) confirmed on the cited page'.format(
        len(data), n_dead, n_chk))
    if dead and not n_dead:
        raise SystemExit('ERROR: dead-link file supplied but nothing matched - check the column')
    # The bands are INJECTED from lifecycle rather than written into the JS. The page must
    # compute days in the BROWSER - it has to run on the reader's clock, not on the clock of
    # whoever built the file - but the THRESHOLDS are policy and belong in one place. Left
    # hard-coded here, a change to lifecycle's bands would silently disagree with this page and
    # nothing would fail; the two would just quietly mean different things by "closing soon".
    page = (PAGE.replace('__DATA__', json.dumps(data, ensure_ascii=False))
                .replace('__DEADHOSTS__', json.dumps(dead_hosts, ensure_ascii=False))
                .replace('__URGENT_DAYS__', str(lifecycle.URGENT_DAYS))
                .replace('__SOON_DAYS__', str(lifecycle.SOON_DAYS))
                .replace('__COUNT__', str(len(data)))
                .replace('__SCOPE__', (f"{client_ctx['name']} &middot; {client_ctx['industry']}"
                                       if client_ctx else scope_label))
                .replace('__SINCE__', (client_ctx['since'] if client_ctx else
                                       (date.fromisoformat(a.date)
                                        - timedelta(days=7)).isoformat()))
                .replace('__DATE__', a.date))
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    with open(a.output, 'w', encoding='utf-8', newline='\n') as h:
        h.write(page)
    print(f"{a.output}  ({len(data)} rows, {os.path.getsize(a.output)//1024} KB)")


if __name__ == '__main__':
    main()
