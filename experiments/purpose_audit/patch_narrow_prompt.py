"""One-off, applied 2026-10-02: add NARROW-FIRST prompts to Markets/run_market_audit.py (upstream's research script, on this machine).
Run once. Refuses if already applied or if an anchor is missing. A backup run_market_audit.pre-narrow-20261002.py is made first.
Design and evidence: experiments/grounding_reliability/RESULT.md; rules and trade-offs in the block comment this inserts."""
import shutil
import sys

P = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/run_market_audit.py"
BAK = "C:/Users/matts/Desktop/Nicolia-PR-Prime/Markets/run_market_audit.pre-narrow-20261002.py"
t = open(P, encoding="utf-8").read()
if "NARROW-FIRST PROMPTS" in t:
    sys.exit("already applied")
shutil.copy(P, BAK)

BLOCK = '''# ============================================================ NARROW-FIRST PROMPTS (2026-10-02) ==
# WHY. The production conference prompt is 11,900 characters and 33 fields. In the 2026-09-30 experiment
# (experiments/grounding_reliability/RESULT.md, cfp-monitor repo) it grounded 9 of 24 calls (38%): 8 hit our own
# 120 s client deadline (the "504"), 7 answered with no search. A 2,850-character prompt asking only for the fields that
# change grounded 24 of 24, in 16 s instead of 28 s, at lower cost, with the same deadline accuracy (24 of 24 equal to the
# known deadline). Saturday 2026-09-27 grounded about a third of calls, so most rows fell back to last week's data.
#
# WHAT THIS DOES. CFP_PROMPT_MODE=narrow-first asks the narrow question on the first NARROW_ATTEMPTS attempts and falls back
# to the unchanged full prompt on the remaining attempts, so the worst case is the old behaviour. Default mode is 'full': a
# caller that does not opt in is unchanged. Fields the narrow answer does not return keep the INPUT row's value (the record is
# built from the input first); the ones this code would otherwise BLANK (FORMAT and VENUE_EVIDENCE_URL for conferences, the
# entry window for awards) are asked for explicitly. CONFERENCE is deliberately NOT asked for, so the model cannot rename an
# event (the experiment's rename note); identity stays the input's.
_NARROW_CONFERENCE_RULES = """    1. STATUS relative to {today_str}: "Closed" if the event or its call closed before today;
       "Open" if the deadline is after today or the form is rolling; "Upcoming" if the event is in
       the future but this edition's call is not published; "Needs Verification" if unconfirmed.
    2. Dates are YYYY-MM-DD. If the page does not confirm a date, return it EMPTY and IS_PROJECTED true.
    3. DEADLINE_EVIDENCE_URL is the exact page where you read the submission deadline.
       DEADLINE_QUOTE is text copied character-for-character from that page containing the deadline.
    4. Never say an event has ended without a page that says so. If you cannot confirm the next
       edition, use STATUS "Needs Verification" - that is not the same as "ended".
    5. FORMAT is "In-Person", "Virtual" or "Hybrid", or empty if the page does not say.
       VENUE_EVIDENCE_URL is the page that states where the event is held, or empty.
    6. Do not rename the event and do not return its name: the identity above is fixed.
    7. RETURN ONLY A VALID JSON OBJECT with exactly these keys: STATUS, STATUS_DETAILS,
       SUBMISSION_DEADLINE, START_DATE, CFP_SUBMISSION_URL, DEADLINE_EVIDENCE_URL, DEADLINE_QUOTE,
       IS_PROJECTED, FORMAT, VENUE_EVIDENCE_URL."""

_NARROW_AWARDS_RULES = """    1. This row is an AWARD or PRIZE PROGRAMME, not a conference. Return the ENTRY / NOMINATION window of
       the programme's own page. Never substitute a conference's call for papers or an event's own speaking deadline.
    2. SUBMISSION_DEADLINE is the date entries CLOSE and SUBMISSION_OPENS the date entries OPEN, both YYYY-MM-DD.
       If a date is not published leave it EMPTY (never a guess, never last cycle's date). ANNOUNCEMENT_DATE is when
       winners are named, YYYY-MM-DD, empty if unpublished.
    3. STATUS relative to {today_str}: "Closed" if entries closed before today; "Open" if entries are open now or the
       form is rolling; "Upcoming" if the award exists but this cycle has not opened; "Needs Verification" if unconfirmed.
    4. A closed cycle is not a dead award: report the cycle you found, name its year in STATUS_DETAILS, and set EDITION.
       Only a statement that the programme has permanently ended justifies saying so, and it needs its own citation.
    5. DEADLINE_EVIDENCE_URL is the exact page where you read the entry deadline (the award's own page, not news about past
       winners). DEADLINE_QUOTE is text copied character-for-character from that page containing the deadline.
       CFP_SUBMISSION_URL is the direct entry or nomination page; MAIN_INFO_URL the programme's own page.
    6. IS_PROJECTED is false only where the entry deadline is explicitly stated for the target cycle on the programme's
       own page; true where it is inferred or unconfirmed.
    7. CFP_MODEL_TYPE is exactly one of "Fixed Deadline", "Rolling Form", "Invitation Only", "Not Announced".
    8. Do not rename the award and do not return its name: the identity above is fixed.
    9. RETURN ONLY A VALID JSON OBJECT with exactly these keys: STATUS, STATUS_DETAILS, SUBMISSION_DEADLINE,
       SUBMISSION_OPENS, ANNOUNCEMENT_DATE, EDITION, CFP_MODEL_TYPE, CFP_SUBMISSION_URL, MAIN_INFO_URL,
       DEADLINE_EVIDENCE_URL, DEADLINE_QUOTE, IS_PROJECTED."""

NARROW_ATTEMPTS = 2


def prompt_mode() -> str:
    """'full' (default, unchanged behaviour) or 'narrow-first'. Read at call time so a test or a launcher can set it."""
    return (os.environ.get('CFP_PROMPT_MODE') or 'full').strip().lower()


def prompt_kind_for_attempt(mode: str, attempt: int, narrow_attempts: int = NARROW_ATTEMPTS) -> str:
    """Which question this attempt asks: narrow on the first `narrow_attempts` attempts of narrow-first mode, else the full prompt."""
    return 'narrow' if (mode == 'narrow-first' and attempt <= narrow_attempts) else 'full'


def build_narrow_prompt(row_dict: dict, today_str: str) -> str:
    """The short question: same identity and anti-echo scaffold as the full prompt, only the fields that change."""
    if cell(row_dict, 'OPPORTUNITY_TYPE').strip().lower() == 'awards':
        return _prompt_scaffold(row_dict, today_str, 'Award', _NARROW_AWARDS_RULES.format(today_str=today_str))
    return _prompt_scaffold(row_dict, today_str, 'Conference', _NARROW_CONFERENCE_RULES.format(today_str=today_str))


'''
ANCHOR = "CITATION_COLUMNS = ('DEADLINE_EVIDENCE_URL', 'VENUE_EVIDENCE_URL',"
if t.count(ANCHOR) != 1:
    sys.exit("anchor 1 missing")
t = t.replace(ANCHOR, BLOCK + ANCHOR, 1)

OLD1 = '''    quota_failures = 0
    prompt = build_grounding_prompt(row_dict, today_str)

    config = types.GenerateContentConfig('''
NEW1 = '''    quota_failures = 0
    _mode = prompt_mode()                      # 'full' (default) or 'narrow-first' - see NARROW-FIRST PROMPTS above
    _full_prompt = build_grounding_prompt(row_dict, today_str)
    _narrow_prompt = build_narrow_prompt(row_dict, today_str) if _mode == 'narrow-first' else None

    config = types.GenerateContentConfig('''
if t.count(OLD1) != 1:
    sys.exit("anchor 2 missing")
t = t.replace(OLD1, NEW1, 1)

OLD2 = '''            limiter.wait()
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

            grounding = grounding_summary(response)
            print(grounding_line(cell(row_dict, 'CONFERENCE') or 'row', grounding))
            GROUNDING_TRAIL.attempt(_tr_label, _tr_market,
                                    cell(row_dict, 'OPPORTUNITY_TYPE'), attempt, grounding)'''
NEW2 = '''            limiter.wait()
            _kind = prompt_kind_for_attempt(_mode, attempt)
            prompt = _narrow_prompt if _kind == 'narrow' else _full_prompt
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

            grounding = grounding_summary(response)
            print(grounding_line(cell(row_dict, 'CONFERENCE') or 'row', grounding) +
                  (f"  [prompt: {_kind}]" if _mode == 'narrow-first' else ""))
            GROUNDING_TRAIL.attempt(_tr_label, _tr_market,
                                    cell(row_dict, 'OPPORTUNITY_TYPE'), attempt, grounding)'''
if t.count(OLD2) != 1:
    sys.exit(f"anchor 3 missing ({t.count(OLD2)})")
t = t.replace(OLD2, NEW2, 1)
open(P, "w", encoding="utf-8").write(t)
print("applied; backup:", BAK)
