"""Plain-English recap of a weekend run, emailed to the operator. (2026-09-27)

    python scripts/weekend_recap.py saturday --log <run_monthly log> [--import-json <json>]
    python scripts/weekend_recap.py sunday   --log <weekly log> --digest <weekly_verify md>
    python scripts/weekend_recap.py monthly  --log <run_monthly log>   (prospect markets)
        [--dry-run]   write the recap beside the log, send nothing

WHY. The weekend jobs ran at 02:00 and 01:00 and reported to a console nobody watched. The
operator found out on Sunday that Saturday had failed, by asking. Every weekend run now ends in
one email that says, in plain words: did it work, the numbers, and what it means for the NEXT
run - Saturday -> Sunday's check -> Monday's customer pages.

Everything reported is DERIVED from the run's own log and files at the moment of sending, never
written down in advance. What Monday will publish comes from publish_guard.check_publish_fresh,
the same function the Monday build calls, so the recap and the build cannot disagree.

Sends through alerts.maybe_send_email to CFP_RECAP_TO (a separate variable from CFP_ALERT_TO, so
switching recaps on does not switch on every older sender). Never raises: a recap that cannot be
sent is written to disk and the run's own exit code is untouched.
"""
from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cfp_monitor.alerts import maybe_send_email                     # noqa: E402
from src.cfp_monitor.publish_guard import check_publish_fresh, manifest_path  # noqa: E402

MARKETS_DIR = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_MARKETS = ("Cybersecurity", "Utility")
CUSTOMER = {"Cybersecurity": "Arnica", "Utility": "Utility Global"}


# ============================================================================ parsing
def first(pattern: str, text: str, group: int = 1, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(group) if m else None


def parse_saturday(log: str) -> dict:
    """The facts a Saturday recap needs, read from run_monthly's log."""
    out: dict = {"markets": {}}
    out["exit"] = first(r"=== run_monthly exit code: (-?\d+) ===", log)
    out["intake"] = first(r"INTAKE HEALTH: (.+)", log)
    if re.search(r"CANARY PASSED", log):
        out["canary"] = "passed"
    elif re.search(r"Canary passed [\d.]+h ago - reusing it", log):
        out["canary"] = "passed earlier today (reused)"
    else:
        out["canary"] = first(r"CANARY FAILED (at stage .+)", log) or (
            "did not run" if "STAGE A" not in log else "did not finish")
    out["stopped"] = first(r"^STOPPED: (.+)$", log, flags=re.M)
    overnight = log.split("=== OVERNIGHT RUN", 1)
    body = overnight[1] if len(overnight) == 2 else ""
    for block in re.split(r"^Market : ", body, flags=re.M)[1:]:
        name = block.split("\n", 1)[0].strip()
        m = {"rows_in": first(r"Rows read: (\d+)", block),
             "written": first(r"written: (\d+) \| in output file", block),
             "requests": first(r"API requests spent this run: (\d+)", block),
             "grounded": first(r"GROUNDING TRAIL: \d+ rows \| (\d+) grounded", block),
             "stubs": first(r"(\d+) row\(s\) written as UNGROUNDED STUBS", block) or "0",
             "composed": first(r"\| (\d+) citation-host-not-in-sources", block) or "0",
             "health": first(r"RUN HEALTH: (\S+)", block),
             # from the audit's own RUN HEALTH tally, not by counting log lines: each 504
             # appears there AND in a retry warning, so a line count doubles it.
             "timeouts": first(r"RUN HEALTH: .*?(\d+) http_504", block) or "0"}
        out["markets"][name] = m
    out["timeouts"] = sum(int(m["timeouts"]) for m in out["markets"].values())
    return out


def parse_digest(md: str) -> list[tuple[str, str, str]]:
    """(category, count, action) rows from the digest's 'At a glance' table."""
    rows = []
    sect = md.split("## At a glance", 1)
    if len(sect) < 2:
        return rows
    for line in sect[1].split("\n## ", 1)[0].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in ("Category", "") and not set(cells[0]) <= {"-", ":"}:
            rows.append((cells[0], cells[1], cells[2]))
    return rows


def monday_outlook(markets_dir: Path, today=None) -> list[tuple[str, bool, str]]:
    out = []
    for m in LIVE_MARKETS:
        ok, why = check_publish_fresh(markets_dir / f"{m}_audited.final.csv", today=today)
        out.append((m, ok, why))
    return out


def promoted_at(markets_dir: Path, market: str) -> str | None:
    try:
        return json.loads(manifest_path(markets_dir / f"{market}_audited.final.csv")
                          .read_text(encoding="utf-8")).get("promoted_at")
    except Exception:
        return None


# ============================================================================ rendering
CSS = ("font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2328;line-height:1.45")
TD = "border:1px solid #d0d7de;padding:6px 10px;text-align:left"


def table(head: list[str], rows: list[list[str]]) -> str:
    h = "".join(f'<th style="{TD};background:#f6f8fa">{H.escape(c)}</th>' for c in head)
    b = "".join("<tr>" + "".join(f'<td style="{TD}">{H.escape(str(c))}</td>' for c in r) + "</tr>"
                for r in rows)
    return f'<table style="border-collapse:collapse;margin:8px 0">{"<tr>" + h + "</tr>"}{b}</table>'


def text_table(head: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    fmt = lambda r: " | ".join(str(c).ljust(w) for c, w in zip(r, widths))  # noqa: E731
    return "\n".join([fmt(head), "-+-".join("-" * w for w in widths)] + [fmt(r) for r in rows])


def pct(a, b) -> str:
    try:
        return f"{a} ({int(a) * 100 // int(b)}%)"
    except (TypeError, ValueError, ZeroDivisionError):
        return str(a)


def monthly_recap(log: str) -> tuple[str, str, str]:
    """The monthly prospect sweep (every 4th Wednesday). Same research as Saturday, but these
    markets have no customer page, so nothing is loaded and nothing downstream changes."""
    s = parse_saturday(log)
    ok = s["exit"] == "0" and bool(s["markets"])
    status = "WORKED" if ok else "FAILED"
    head = ["Market", "Rows done", "Researched with real searches", "Not researched",
            "AI requests"]
    rows = [[n, f"{m['written']} of {m['rows_in']}", pct(m["grounded"], m["rows_in"]),
             m["stubs"], m["requests"]] for n, m in s["markets"].items()]
    total_req = sum(int(m["requests"] or 0) for m in s["markets"].values())
    facts = [f"5-row test before the run: {s['canary']}.",
             f"AI requests in total: about {total_req}."]
    if s["timeouts"]:
        facts.append(f"Google was slow: {s['timeouts']} '504' timeouts (Google's server took "
                     f"too long to answer and gave up). Each retry costs a request.")
    if s["stopped"]:
        facts.append(f"The run stopped early: {s['stopped']}")
    means = ["These markets have no customer page, so the results stay in the Markets folder "
             "and are NOT loaded into the database - by design.",
             "Nothing changes for Arnica or Utility Global, Sunday's check or Monday's pages."]
    subject = f"CFP monthly research (prospect markets) {status} - {datetime.now():%a %b %d}"
    html_ = "".join([f'<div style="{CSS}">',
                     f"<h2 style='margin:0 0 8px'>Monthly research, markets without a customer: {status}</h2>",
                     table(head, rows) if rows else "<p><b>No market was researched.</b></p>",
                     "<ul>" + "".join(f"<li>{H.escape(f)}</li>" for f in facts) + "</ul>",
                     "<h3 style='margin:14px 0 4px'>What this means next</h3>",
                     "<ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in means) + "</ul></div>"])
    text = "\n\n".join([f"Monthly research, markets without a customer: {status}",
                        text_table(head, rows) if rows else "No market was researched.",
                        "\n".join("- " + f for f in facts),
                        "What this means next:\n" + "\n".join("- " + x for x in means)])
    return subject, text, html_


def saturday_recap(log: str, imp: dict | None, markets_dir: Path) -> tuple[str, str, str]:
    s = parse_saturday(log)
    research_ok = s["exit"] == "0" and bool(s["markets"])
    head = ["", *s["markets"].keys()]
    rows = [
        ["Rows done", *[f"{m['written']} of {m['rows_in']}" for m in s["markets"].values()]],
        ["Researched with real Google searches",
         *[pct(m["grounded"], m["rows_in"]) for m in s["markets"].values()]],
        ["Not researched (kept last week's info)", *[m["stubs"] for m in s["markets"].values()]],
        ["AI requests used", *[m["requests"] for m in s["markets"].values()]],
    ]
    total_req = sum(int(m["requests"] or 0) for m in s["markets"].values())

    facts = [f"5-row test before the run: {s['canary']}.",
             f"Customer sheet check-in: {s['intake'] or 'no result in the log'}.",
             f"AI requests in total: about {total_req}."]
    if s["timeouts"]:
        facts.append(f"Google was slow: {s['timeouts']} '504' timeouts (Google's server took too "
                     f"long to answer and gave up). Each retry costs a request.")
    if s["stopped"]:
        facts.append(f"The run stopped early: {s['stopped']}")

    # What the automatic import did
    imp_rows, imp_lines = [], []
    if imp:
        for m in imp.get("markets", []):
            if m.get("status") in ("PROMOTED", "ACCEPTED"):
                imp_rows.append([m["market"], str(m.get("from_this_week")),
                                 str(m.get("from_last_week")), str(m.get("held_back")),
                                 "yes" if m["status"] == "PROMOTED" else "NO"])
            else:
                imp_lines.append(f"{m['market']}: NOT loaded - {m.get('why', m.get('status'))}")
        db_line = ("The database now holds this weekend's research."
                   if imp.get("database") == "updated" else
                   "The database was NOT changed - it still holds last week's information.")
    else:
        db_line = "The automatic load into the database did not run."

    # What it means next
    sunday = ("Sunday 1 AM check: will check THIS weekend's research."
              if imp and imp.get("database") == "updated" else
              "Sunday 1 AM check: will run, but on LAST week's information.")
    monday = []
    for m, ok, why in monday_outlook(markets_dir):
        who = CUSTOMER.get(m, m)
        monday.append(f"Monday 7 AM page ({who}): " + (
            f"will publish - {why}" if ok else f"will NOT publish - {why}"))

    good = research_ok and imp and imp.get("status") == "DONE"
    status = ("WORKED" if good else "PARTLY WORKED" if research_ok else "FAILED")
    subject = f"CFP Saturday research {status} - {datetime.now():%a %b %d}"

    html_parts = [f'<div style="{CSS}">',
                  f"<h2 style='margin:0 0 8px'>Saturday research: {status}</h2>",
                  table(head, rows) if s["markets"] else "<p><b>No market was researched.</b></p>",
                  "<ul>" + "".join(f"<li>{H.escape(f)}</li>" for f in facts) + "</ul>",
                  "<h3 style='margin:14px 0 4px'>Loaded into the database automatically</h3>"]
    if imp_rows:
        html_parts.append(table(["Market", "This week's research", "Kept last week's version",
                                 "Held back", "Ready for Monday"], imp_rows))
    html_parts.append("<ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in imp_lines + [db_line])
                      + "</ul>")
    html_parts += ["<h3 style='margin:14px 0 4px'>What this means next</h3>",
                   "<ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in [sunday] + monday) + "</ul>",
                   "</div>"]
    text = "\n\n".join([f"Saturday research: {status}",
                        text_table(head, rows) if s["markets"] else "No market was researched.",
                        "\n".join("- " + f for f in facts),
                        "Loaded into the database automatically:\n"
                        + (text_table(["Market", "This week", "Kept last week", "Held back",
                                       "Ready for Monday"], imp_rows) + "\n" if imp_rows else "")
                        + "\n".join("- " + x for x in imp_lines + [db_line]),
                        "What this means next:\n" + "\n".join("- " + x for x in [sunday] + monday)])
    return subject, text, "".join(html_parts)


def sunday_recap(log: str, digest: str, markets_dir: Path,
                 exit_code: str | None = None) -> tuple[str, str, str]:
    # run_weekly.bat echoes its exit code to the console, not the log, so the caller passes it.
    exit_code = exit_code if exit_code is not None else first(r"Finished with exit code (-?\d+)", log)
    glance = parse_digest(digest)
    worked = exit_code == "0" and bool(glance)
    status = "WORKED" if worked else "FAILED"
    fresh = []
    for m in LIVE_MARKETS:
        p = promoted_at(markets_dir, m)
        fresh.append(f"{CUSTOMER.get(m, m)}: the research this check covered was approved "
                     + (f"on {p[:16].replace('T', ' at ')}" if p else
                        "by hand, with no approval record (before automatic loading existed)"))
    rows = [[c, n, a] for c, n, a in glance]
    needs = sum(int(n) for _, n, _ in glance if n.isdigit())
    monday = []
    for m, ok, why in monday_outlook(markets_dir):
        who = CUSTOMER.get(m, m)
        monday.append(f"Monday 7 AM page ({who}): " + (
            f"will publish - {why}" if ok else f"will NOT publish - {why}"))
    subject = f"CFP Sunday link check {status} - {datetime.now():%a %b %d}"
    facts = ([f"{needs} item(s) need someone to act." if glance else
              "The check wrote no summary - see the log."] + fresh)
    html_ = "".join([f'<div style="{CSS}">',
                     f"<h2 style='margin:0 0 8px'>Sunday link and deadline check: {status}</h2>",
                     table(["What", "Count", "What happens"], rows) if rows else "",
                     "<ul>" + "".join(f"<li>{H.escape(f)}</li>" for f in facts) + "</ul>",
                     "<h3 style='margin:14px 0 4px'>What this means next</h3>",
                     "<ul>" + "".join(f"<li>{H.escape(x)}</li>" for x in monday) + "</ul></div>"])
    text = "\n\n".join([f"Sunday link and deadline check: {status}",
                        text_table(["What", "Count", "What happens"], rows) if rows else "",
                        "\n".join("- " + f for f in facts),
                        "What this means next:\n" + "\n".join("- " + x for x in monday)])
    return subject, text, html_


# ============================================================================ main
def main() -> int:
    ap = argparse.ArgumentParser(description="Email a plain-English weekend run recap.")
    ap.add_argument("kind", choices=["saturday", "sunday", "monthly"])
    ap.add_argument("--log", required=True)
    ap.add_argument("--import-json", help="weekend_import.py's report (saturday)")
    ap.add_argument("--digest", help="weekly_verify's markdown digest (sunday)")
    ap.add_argument("--exit-code", help="the run's exit code, when its log does not record it")
    ap.add_argument("--markets-dir", default=str(MARKETS_DIR))
    ap.add_argument("--dry-run", action="store_true", help="write the recap to disk, send nothing")
    a = ap.parse_args()
    md = Path(a.markets_dir)
    try:
        log = Path(a.log).read_text(encoding="utf-8-sig", errors="replace")
        if a.kind == "saturday":
            imp = None
            if a.import_json and Path(a.import_json).exists():
                imp = json.loads(Path(a.import_json).read_text(encoding="utf-8"))
            subject, text, html_ = saturday_recap(log, imp, md)
        elif a.kind == "monthly":
            subject, text, html_ = monthly_recap(log)
        else:
            digest = Path(a.digest).read_text(encoding="utf-8") if a.digest and Path(a.digest).exists() else ""
            subject, text, html_ = sunday_recap(log, digest, md, a.exit_code)
    except Exception as e:                       # a recap must never break the run it reports on
        subject = f"CFP {a.kind} run - recap could not be built"
        text = f"The {a.kind} run finished, but its recap failed: {type(e).__name__}: {e}\nLog: {a.log}"
        html_ = None
    out = Path(a.log).with_suffix(".recap.html")
    out.write_text(html_ or f"<pre>{H.escape(text)}</pre>", encoding="utf-8")
    print(subject)
    print(text)
    if a.dry_run:
        print(f"\n(dry run - recap written to {out}, not sent)")
        return 0
    try:
        sent = maybe_send_email(subject, text, html=html_, to_env="CFP_RECAP_TO")
        print("recap emailed" if sent else "recap NOT emailed - CFP_RECAP_TO or CFP_SMTP_* not set")
    except Exception as e:
        print(f"recap NOT emailed - {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
