"""Free re-score of the fields probe_narrow.py asked for but did not check. NO Gemini calls, no network.

Reads the saved answers (calls.jsonl) and compares them with what the database already holds for the same
12 events (read-only). Writes rescored_fields.json here. Nothing else is touched.
"""
import os, json, re, sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CFP-Monitor", "cfp_monitor.db")   # the live database, read-only here
sample = json.loads((HERE / "sample.json").read_text(encoding="utf-8"))
calls = [json.loads(l) for l in (HERE / "calls.jsonl").read_text(encoding="utf-8").splitlines()]

c = sqlite3.connect(f"file:///{DB.replace(chr(92), '/')}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
truth = {}
for s in sample:
    r = c.execute("select * from grounding_facts where name=? and verify_state='verified' and deadline>='2026-10-01'",
                  (s["row"]["CONFERENCE"],)).fetchone()
    truth[s["row"]["CONFERENCE"]] = dict(r) if r else {}

norm = lambda s: re.sub(r"\s+", " ", (s or "")).strip().lower()
host = lambda u: re.sub(r"^https?://(www\.)?", "", u or "").split("/")[0].lower()
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]


def date_in_quote(quote, iso):
    """Does the quote state the deadline date in some written form (day + month, or the ISO string)?"""
    if not quote or not iso:
        return False
    y, m, d = iso.split("-")
    q = quote.lower()
    mon, dd = MONTHS[int(m) - 1], str(int(d))
    return (iso in q or bool(re.search(rf"\b{dd}(st|nd|rd|th)?\b.{{0,12}}\b{mon[:3]}", q))
            or bool(re.search(rf"\b{mon[:3]}[a-z]*\.?\s*{dd}\b", q)))


rows = []
for cl in calls:
    if cl["outcome"] != "ok_searched":
        continue
    t = truth[cl["row"]]
    m = re.search(r"\{.*\}", cl["text"], re.S)
    d = json.loads(m.group(0)) if m else {}
    tq, aq = norm(sample[cl["i"]]["truth"]["quote"]), norm(d.get("DEADLINE_QUOTE"))
    details = (d.get("STATUS_DETAILS") or "").lower()
    rows.append({
        "arm": cl["arm"], "row": cl["row"],
        "name_same": norm(d.get("CONFERENCE")) == norm(cl["row"]),
        "status": d.get("STATUS"), "status_truth": t.get("status"),
        "start_ok": (d.get("START_DATE") or "") == (t.get("start_date") or ""),
        "start_ans": d.get("START_DATE"), "start_truth": t.get("start_date"),
        "projected_ans": d.get("IS_PROJECTED"), "projected_truth": t.get("is_projected"),
        "cfp_url_same": (d.get("CFP_SUBMISSION_URL") or "").rstrip("/") == (t.get("submission_url") or "").rstrip("/"),
        "cfp_host_same": bool(d.get("CFP_SUBMISSION_URL")) and host(d.get("CFP_SUBMISSION_URL")) == host(t.get("submission_url")),
        "cfp_url_blank": not d.get("CFP_SUBMISSION_URL"),
        "quote_blank": not aq,
        "quote_equals_truth": bool(aq) and aq == tq,
        "quote_contains_or_within_truth": bool(aq) and (aq in tq or tq in aq),
        "quote_states_deadline": date_in_quote(d.get("DEADLINE_QUOTE"), sample[cl["i"]]["truth"]["deadline"]),
        "details_claims_ended": bool(re.search(r"\b(ended|discontinued|cancel|no longer|permanently)\b", details)),
        "details_blank": not details.strip(),
    })

out = {}
for arm in ("A", "E"):
    rs = [r for r in rows if r["arm"] == arm]
    n = len(rs)
    out[arm] = {
        "grounded_calls": n,
        "name_unchanged": sum(r["name_same"] for r in rs),
        "status_equals_db": sum(str(r["status"]).lower() == str(r["status_truth"]).lower() for r in rs),
        "start_date_equals_db": sum(r["start_ok"] for r in rs),
        "is_projected_false_like_db": sum(str(r["projected_ans"]).lower() == str(r["projected_truth"]).lower() for r in rs),
        "cfp_url_identical_to_db": sum(r["cfp_url_same"] for r in rs),
        "cfp_url_same_host_as_db": sum(r["cfp_host_same"] for r in rs),
        "cfp_url_blank": sum(r["cfp_url_blank"] for r in rs),
        "quote_blank": sum(r["quote_blank"] for r in rs),
        "quote_identical_to_our_verified_quote": sum(r["quote_equals_truth"] for r in rs),
        "quote_overlaps_our_verified_quote": sum(r["quote_contains_or_within_truth"] for r in rs),
        "quote_actually_states_the_deadline": sum(r["quote_states_deadline"] for r in rs),
        "details_claims_event_ended": sum(r["details_claims_ended"] for r in rs),
        "details_blank": sum(r["details_blank"] for r in rs),
    }
(HERE / "rescored_fields.json").write_text(json.dumps({"summary": out, "rows": rows}, indent=1), encoding="utf-8")
print(json.dumps(out, indent=1))
print("\nstatus values in DB truth:", sorted({str(t.get('status')) for t in truth.values()}),
      "| DB is_projected values:", sorted({str(t.get('is_projected')) for t in truth.values()}))
bad = [(r["arm"], r["row"][:30], r["start_ans"], r["start_truth"]) for r in rows if not r["start_ok"]][:8]
print("start-date mismatches (sample):", bad)
