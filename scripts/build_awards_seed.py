"""Build the awards seed list from the customer awards sheets.

The seed is a KNOWN-NAME SET, not a set of rows to repair. Across both sheets there
are 135 rows and 2 live deadlines; the value is telling discovery what we already
carry so it hunts the unannounced cycles instead of re-finding these.

Three things this script is deliberate about:

1. COLUMN NAMES ARE THE GENERATOR'S, NOT THE SHEETS'.
   run_market_audit.py is hardcoded to 'CONFERENCE' - generate_event_id() reads
   record.get('CONFERENCE', ''), so a seed keyed on 'AWARD' yields empty EVENT_IDs
   with no error. Until the generator takes a --name-col (stage 3), the seed speaks
   the generator's dialect and OPPORTUNITY_TYPE marks what the rows really are.

2. THE CUSTOMER LAYER PASSES THROUGH UNTOUCHED.
   PRIORITY, STATUS, STATUS DETAILS and NOTES belong to the customer under contract
   section 3. Copied verbatim, never normalised, never inferred. Arnica calls the
   column STATUS and Utility Global calls it SUBMISSION STATUS; that is a name
   difference, not a value difference.

3. DUPLICATES ARE REPORTED, NOT MERGED.
   Utility Global carries two apparent duplicate pairs. Collapsing them would hide a
   disagreement that belongs to the customer to resolve (2.1: a label, never a
   deletion).

Read-only against Downloads; writes one new CSV. Touches no database.
"""
import argparse
import collections
import csv
import os
import re
import sys

# The 21-column input convention, from Markets/*_input.csv, plus four awards
# columns. The extras are appended so nothing positional shifts.
INPUT_COLS = [
    'CONFERENCE', 'CONFERENCE URL', 'LOCATION', 'CONFERENCE DATES', 'LATEST UPDATE',
    'SUBMISSION DEADLINE', 'SUBMISSION DATE VERIFIED', 'PRIORITY', 'STATUS',
    'STATUS DETAILS', 'CFP MODEL TYPE', 'SUBMISSION URL', 'COORDINATOR EMAIL',
    'OVERVIEW', 'CATEGORIES', 'NOTES', 'TRACK', 'RESEARCH STATUS', 'EDITION',
    'START DATE', 'Market',
]
AWARDS_COLS = ['OPPORTUNITY_TYPE', 'ANNOUNCEMENT', 'OPERATOR', 'SOURCE_SHEET',
               'DUP_OF', 'SEED_FLAGS', 'SEED_DISCARDED']
SEED_COLS = INPUT_COLS + AWARDS_COLS

# Customer-owned under contract section 3. Copied verbatim; listed here so the
# intent is greppable rather than implicit.
CUSTOMER_OWNED = ('PRIORITY', 'STATUS', 'STATUS DETAILS', 'NOTES')

SHEETS = [
    {
        'file': 'Arnica Awards 2026 - Awards.csv',
        'market': 'Cybersecurity',
        'client': 'Arnica',
        # Arnica names the customer status column STATUS.
        'status_col': 'STATUS',
    },
    {
        'file': 'Utility Global Award List 2026 - Awards.csv',
        'market': 'Utility',
        'client': 'Utility Global',
        # Utility Global names the same field SUBMISSION STATUS. Keying on one name
        # alone reads the other sheet as entirely blank - the 'CONFERENCE ' class of
        # bug that customer-sheet-matching.md warns produces a confident wrong 0%.
        'status_col': 'SUBMISSION STATUS',
    },
]


def read_sheet(path):
    """Rows with stripped header keys. Trailing whitespace in their headers is real."""
    with open(path, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        clean = {(k or '').strip(): (v or '') for k, v in r.items()}
        if clean.get('AWARD', '').strip():
            out.append(clean)
    return out


def operator_of(url):
    """Registrable-ish host of the submission URL.

    Award operators run several programmes each (globeeawards, cyberdefenseawards,
    RSA), so one crawl of an operator can yield several award records. That is
    leverage conferences do not have. A blank URL gives a blank operator - never a
    guess.
    """
    url = (url or '').strip()
    if '//' not in url:
        return ''
    host = url.split('//', 1)[1].split('/', 1)[0].lower()
    if host.startswith('www.'):
        host = host[4:]
    return host


DATE_SHAPED = re.compile(r'^\s*(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})')


def categories_holds_url(src):
    """CATEGORIES containing a URL rather than category names.

    Measured 2026-09-03: 24 of 71 Utility Global rows, 12 of them EXACTLY equal to
    SUBMISSION URL. Arnica: 0 of 64. That equality is the tell - this is residual
    text from copy/pasting column J (SUBMISSION URL) across, so on those rows the
    value is not weak category data, it is NOT CATEGORY DATA AT ALL.

    So the seed drops it rather than carrying a known-wrong value forward (2.6: an
    honest blank beats a confident guess), keeping the original in SEED_DISCARDED so
    nothing is lost (2.1: a label, never a deletion). Their sheet is not touched -
    this is our copy.
    """
    return (src.get('CATEGORIES', '') or '').strip().lower().startswith('http')


def announcement_displaced(src):
    """On a categories-holds-url row, a non-date ANNOUNCEMENT is likely shifted text.

    ANNOUNCEMENT should carry when winners are named. On these rows it sometimes
    holds the category text CATEGORIES should have had ("Clean energy impact
    (brand/project categories)") and sometimes a perfectly good date ("03/22/2026").
    Mixed, so it is FLAGGED for re-derivation and never moved: relocating a value
    across columns on our own inference is the guess 2.5 says to decline.
    """
    ann = (src.get('ANNOUNCEMENT', '') or '').strip()
    return bool(ann) and not DATE_SHAPED.match(ann)


def build_row(src, sheet, lineno):
    name = src['AWARD'].strip()
    sub_url = src.get('SUBMISSION URL', '').strip()
    categories = src.get('CATEGORIES', '').strip()

    flags, discarded = [], []
    if categories_holds_url(src):
        # Residual paste from SUBMISSION URL - drop it rather than let anything
        # downstream read a URL as a category.
        flags.append('categories-holds-url')
        discarded.append('CATEGORIES=%s' % categories)
        if categories == sub_url:
            flags.append('categories-equals-submission-url')
        categories = ''
        if announcement_displaced(src):
            flags.append('announcement-not-a-date')

    row = {c: '' for c in SEED_COLS}
    row.update({
        'CONFERENCE': name,
        # Awards sheets carry no separate award URL. An honest blank beats a guessed
        # root (2.6); discovery fills it.
        'CONFERENCE URL': '',
        'LOCATION': src.get('LOCATION', '').strip(),
        'CONFERENCE DATES': src.get('EVENT DATE', '').strip(),
        'LATEST UPDATE': src.get('LATEST UPDATE', '').strip(),
        'SUBMISSION DEADLINE': src.get('SUBMISSION DEADLINE', '').strip(),
        'SUBMISSION DATE VERIFIED': src.get('SUBMISSION DATE VERIFIED', '').strip(),
        'SUBMISSION URL': sub_url,
        'COORDINATOR EMAIL': src.get('COORDINATOR CONTACT', '').strip(),
        'OVERVIEW': src.get('OVERVIEW', '').strip(),
        'CATEGORIES': categories,
        'Market': sheet['market'],
        'OPPORTUNITY_TYPE': 'Awards',
        'ANNOUNCEMENT': src.get('ANNOUNCEMENT', '').strip(),
        'OPERATOR': operator_of(sub_url),
        'SOURCE_SHEET': '%s:%d' % (sheet['client'], lineno),
        'DUP_OF': '',
        'SEED_FLAGS': ';'.join(flags),
        'SEED_DISCARDED': ' | '.join(discarded),
    })
    # Customer-owned fields, verbatim - no strip-and-retitle, no inference.
    row['PRIORITY'] = src.get('PRIORITY', '')
    row['STATUS'] = src.get(sheet['status_col'], '')
    row['STATUS DETAILS'] = src.get('STATUS DETAILS', '')
    row['NOTES'] = src.get('NOTES', '')
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--downloads', default=os.path.expanduser(r'~\Downloads'),
                    help='where the two sheet exports were downloaded')
    ap.add_argument('-o', '--out', required=True, help='seed CSV to write')
    args = ap.parse_args()

    seed, dupes, missing_url = [], [], []
    per_sheet = {}

    for sheet in SHEETS:
        path = os.path.join(args.downloads, sheet['file'])
        if not os.path.exists(path):
            sys.exit('ERROR: missing export %s\n'
                     'Re-export via /export?format=csv&gid= in an authenticated\n'
                     'browser session. Never /gviz/tq - it is lossy.' % path)
        rows = read_sheet(path)
        per_sheet[sheet['client']] = len(rows)

        seen = {}
        for i, src in enumerate(rows, start=2):  # +2: header is line 1
            row = build_row(src, sheet, i)
            key = row['CONFERENCE'].strip().lower()
            if key in seen:
                # Label the later copy so stage 4 can skip it without deleting
                # anything (2.1: a label, never a deletion). The first copy stays
                # authoritative because it is the one the customer has worked.
                first = seen[key]
                row['DUP_OF'] = first['SOURCE_SHEET']
                dupes.append((sheet['client'], key, first['SOURCE_SHEET'],
                              row['SOURCE_SHEET']))
            else:
                seen[key] = row
            if not row['SUBMISSION URL']:
                missing_url.append((sheet['client'], row['CONFERENCE']))
            seed.append(row)

    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=SEED_COLS)
        w.writeheader()
        w.writerows(seed)

    # Every number below is computed from the rows just written, never written down.
    print('Wrote %s' % args.out)
    print('  %d rows, %d columns' % (len(seed), len(SEED_COLS)))
    for client, n in per_sheet.items():
        print('    %-16s %d' % (client, n))

    verified = sum(1 for r in seed if r['SUBMISSION DATE VERIFIED'].strip() == 'Verified')
    prioritised = sum(1 for r in seed if r['PRIORITY'].strip())
    with_status = sum(1 for r in seed if r['STATUS'].strip())
    print('  customer layer carried through (contract s3, read-only):')
    print('    %d Verified, %d with PRIORITY, %d with STATUS' %
          (verified, prioritised, with_status))

    ops = collections.Counter(r['OPERATOR'] for r in seed if r['OPERATOR'])
    multi = [(n, h) for h, n in ops.items() if n > 1]
    print('  %d distinct operators; %d run more than one programme'
          % (len(ops), len(multi)))
    for n, h in sorted(multi, reverse=True)[:8]:
        print('      %-32s %d' % (h, n))

    flagged = [r for r in seed if r['SEED_FLAGS']]
    to_research = sum(1 for r in seed if not r['DUP_OF'])
    print('  %d rows to research (%d labelled DUP_OF and skippable)'
          % (to_research, len(seed) - to_research))

    if dupes:
        print('  DUPLICATE NAMES - labelled, not merged (2.1):')
        for client, key, first, later in dupes:
            print('      %-16s %-40s keep %-18s dup %s'
                  % (client, key[:40], first, later))
    if flagged:
        tally = collections.Counter(f for r in flagged for f in r['SEED_FLAGS'].split(';'))
        print('  %d rows carry a seed flag (their sheet untouched; our copy cleaned):'
              % len(flagged))
        for f, n in tally.most_common():
            print('      %-34s %d' % (f, n))
        blanked = sum(1 for r in seed if r['SEED_DISCARDED'])
        print('      -> CATEGORIES blanked on %d rows, original kept in SEED_DISCARDED'
              % blanked)
    cats = sum(1 for r in seed if r['CATEGORIES'].strip())
    print('  usable CATEGORIES after cleaning: %d of %d' % (cats, len(seed)))
    if missing_url:
        print('  %d rows with no SUBMISSION URL:' % len(missing_url))
        for client, name in missing_url[:8]:
            print('      %-16s %s' % (client, name[:56]))


if __name__ == '__main__':
    main()
