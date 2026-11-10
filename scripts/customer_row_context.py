"""The customer's own sheet row as research CONTEXT: the weekly CUSTOMER_ROW writer and its offline rehearsal (customer-context plan steps 2, 3, 6).

    python scripts/customer_row_context.py --markets Awards                       # report only: says what it would write, writes nothing
    python scripts/customer_row_context.py --markets Cybersecurity,Utility --apply # Saturday step 0a4 (Friday: --markets Awards --apply)
    python scripts/customer_row_context.py --markets Awards --clear                # the switch is off: empty the column
    python scripts/customer_row_context.py --rehearse                              # every prompt of both nights, built offline: counts and growth

WHY. Nothing from the customer's row reached the research prompt (docs/design/customer-context-plan.md, "What exists today").
D9 on Daily Review (Matt, 2026-11-09): event facts (name, link, place, dates, their deadline, their submission link) plus their STATUS DETAILS
and NOTES, with contacts, emails and phone numbers KEPT ("sometimes the process is to send inquiry to a certain email address"). Clarified the
same evening (Matt in chat, relayed by the parent session: "Yes, include both"): their one-word STATUS and the COORDINATOR CONTACT column too.
LOGIN and PW are never copied: no such column is read here (the snapshot job drops them), and a cell carrying a login or password pattern is
dropped and counted. D10: live from Friday 11-13 (awards) and Saturday 11-14 (conferences).

CONTEXT, NEVER EVIDENCE (contract 2.1, 2.6 and section 3). The cell says so; the prompt patch (docs/control/patches/ACT-72-*) tells the model
to use it to find the right event, never to copy a value from it, to write both in STATUS_DETAILS where the event's own page differs, and never
to return NOTES or the customer's contact as a value. Their STATUS is context about where THEY stand; it is never a value we return.

SOURCES. Conference rows: the client layer (client_conferences, loaded by Saturday's step 0 intake BEFORE this step), paired with input rows by
the coverage rule (customer_row_answers.context_rows: our canonical id, else the same URL with a date within 30 days). Award rows: the newest
copies of the two customer awards sheets (refreshed by Friday's step 0a1b), paired by name key or deep link, never an id. It runs LAST before
the research (step 0a4, after the id stamping and the refresh plan), so no later writer drops the column.

WRITE (--apply). Rewrites only the CUSTOMER_ROW column of <Market>_input.csv (added at the end when missing; cleared first, so a row that no
longer pairs loses its old cell). Once-a-day backup <Market>_input.pre-context.csv; then a read-back: same row count, same other columns in the
same order, every other cell equal, CUSTOMER_ROW exactly as intended. Any difference puts the file back as it was (FAILED).

VERDICT (QbD). One line, which the recap repeats:
    CUSTOMER CONTEXT: HEALTHY|DEGRADED|FAILED - n of m research rows carry the customer's row (k from awards sheets); ...; evidence <file>
DEGRADED when a customer sheet copy is missing or older than 2 days, or a cell was dropped for a login or password pattern. FAILED when the
context could not be built or a write was put back. Exit 0 / 2 / 1; the caller ignores the exit code: it can never stop the research. Evidence
(per row: market, row, id, conference, chars; per refusal: why) goes to runs_out/qa/<cycle>/ - OUTSIDE the repo: the cells hold the customer's
text and contacts (D9), and this repository is public. Nothing here prints a cell.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import re
import shutil
import sqlite3
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
LIVE_DB = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor\cfp_monitor.db")
PROMPT_PATCH = ROOT / "docs" / "control" / "patches" / "ACT-72-run_market_audit.py.patch"
COLUMN = "CUSTOMER_ROW"
CONF_MARKETS = ("Cybersecurity", "Utility")
ALL_MARKETS = ("Awards", *CONF_MARKETS)
MAX_FREE_TEXT = 600              # per STATUS DETAILS / NOTES: room for a sentence of process and an address, a bounded prompt
STALE_AFTER_DAYS = 2
CONF_SNAPSHOT_DIRS = {"arnica": "arnica", "utility-global": "utility"}            # client_key -> customer_snapshots/<dir> (the intake's copies)
AWARD_CLIENTS = ("arnica-awards", "utility-awards")
CLIENT_LABEL = {"arnica": "Arnica", "utility-global": "Utility Global", "arnica-awards": "Arnica", "utility-awards": "Utility Global"}
# Codex review 2026-11-09 (finding 2): a password word ANYWHERE drops the cell ("portal password is ..."); a login or user name only when it is
# given ("login: x", "username is x"), so process text such as "login required to submit" is kept.
LOGIN_PATTERN = re.compile(r"\b(password|passwd|pwd)\b|\bpw\s*[:=]|\b(log-?in|user ?name)\s*(:|=|\bis\b)", re.I)
LEAD = "CUSTOMER ROW (context, not evidence)"


# ------------------------------------------------------------------ the cell (pure)
def _flat(v, cap: int | None = None) -> str:
    s = re.sub(r"\s+", " ", str(v if v is not None else "")).strip()
    if s.lower() in ("nan", "none", "n/a", "-"):
        return ""
    if cap and len(s) > cap:
        s = s[:cap].rstrip() + " (cut)"
    return s


def context_cell(label: str, f: dict) -> str:
    """ONE customer row as one cell; '' when nothing is filled in. `f` keys: name, link, place, dates, deadline, submission_link, status,
    status_details, notes, contact. A blank is left out, never a placeholder. Contacts are KEPT as written (D9 and its clarification)."""
    parts = [f'name "{_flat(f.get("name"))}"'] if _flat(f.get("name")) else []
    for key, word in (("link", "link"), ("place", "place"), ("dates", "dates"), ("deadline", "their deadline"),
                      ("submission_link", "their submission link"), ("status", "their status")):
        v = _flat(f.get(key))
        if v:
            parts.append(f"{word} {v}")
    for key, word in (("status_details", "their status details"), ("notes", "their notes"), ("contact", "their coordinator contact")):
        v = _flat(f.get(key), MAX_FREE_TEXT)
        if v:
            parts.append(f"{word}: {v}")
    return f"{LEAD} - {label} sheet: " + " | ".join(parts) + "." if parts else ""


def conference_fields(r: dict) -> dict:
    """From a client_conferences row (the client layer)."""
    return {"name": r.get("their_name"), "link": r.get("their_url"), "place": r.get("location"), "dates": r.get("event_start_date"),
            "deadline": r.get("their_deadline"), "submission_link": r.get("their_submission_url"), "status": r.get("status"),
            "status_details": r.get("status_details"), "notes": r.get("notes"), "contact": r.get("coordinator_contact")}


def award_fields(r: dict) -> dict:
    """From a raw row of an awards-sheet copy (the copy's own column names)."""
    return {"name": r.get("AWARD"), "link": "", "place": r.get("LOCATION"), "dates": r.get("EVENT DATE"), "deadline": r.get("SUBMISSION DEADLINE"),
            "submission_link": r.get("SUBMISSION URL"), "status": r.get("STATUS") or r.get("SUBMISSION STATUS"),
            "status_details": r.get("STATUS DETAILS"), "notes": r.get("NOTES"), "contact": r.get("COORDINATOR CONTACT")}


# ------------------------------------------------------------------ pairing (pure)
def conference_cells(client_rows: list[dict], inputs: dict[str, list[dict]], up_to_canon: dict[str, str]) -> dict[tuple[str, int], str]:
    """{(market, input row index): cell}, by the coverage pairing of customer_row_answers.context_rows (one rule, not a second copy)."""
    from scripts import customer_row_answers as cra

    def cell(r):
        return context_cell(CLIENT_LABEL.get(r.get("client_key", ""), "customer"), conference_fields(r))

    return {(x["market"], x["index"]): x["CUSTOMER_ROW"] for x in cra.context_rows(client_rows, inputs, up_to_canon, text=cell, with_index=True)}


def award_cells(sheets: dict[str, list[dict]], inputs: list[dict]) -> dict[int, str]:
    """{awards input row index: cell}, by name key, else a deep submission link (customer_awards.name_key / url_key). Never an id: the sheets
    carry none. Several sheet rows for one award are joined."""
    from scripts.customer_awards import name_key, url_key
    by_name: dict[str, list[str]] = {}
    by_url: dict[str, list[str]] = {}
    for client, rows in sheets.items():
        for r in rows:
            c = context_cell(CLIENT_LABEL.get(client, client), award_fields(r))
            if not c:
                continue
            if name_key(r.get("AWARD") or ""):
                by_name.setdefault(name_key(r["AWARD"]), []).append(c)
            if url_key(r.get("SUBMISSION URL") or ""):
                by_url.setdefault(url_key(r["SUBMISSION URL"]), []).append(c)
    out: dict[int, str] = {}
    for i, inp in enumerate(inputs):
        if (inp.get("DUP_OF") or "").strip():
            continue
        # The deep link first (Codex review 2026-11-09, finding 1): two different awards can share a name key, a deep link names one.
        cells: list[str] = []
        for u in (inp.get("SUBMISSION URL") or "", inp.get("CONFERENCE URL") or ""):
            cells = by_url.get(url_key(u), []) if url_key(u) else []
            if cells:
                break
        if not cells and name_key(inp.get("CONFERENCE") or ""):
            cells = by_name.get(name_key(inp["CONFERENCE"]), [])
        if cells:
            out[i] = " || ".join(dict.fromkeys(cells))
    return out


def screen(cells: dict[int, str], market: str, refused: list[dict]) -> dict[int, str]:
    """Drop a cell that carries a login or password pattern (never copied, D9). The refusal names the row, never the text."""
    keep = {}
    for i, c in cells.items():
        if LOGIN_PATTERN.search(c):
            refused.append({"market": market, "row": i + 2, "why": "a login or password pattern: cell dropped"})
        else:
            keep[i] = c
    return keep


# ------------------------------------------------------------------ files
def read_csv(p: Path) -> tuple[list[str], list[dict]]:
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def newest_copy(folder: Path) -> Path | None:
    files = sorted(Path(folder).glob("*.csv"), key=lambda p: p.stat().st_mtime) if Path(folder).is_dir() else []
    return files[-1] if files else None


def copy_age_days(p: Path | None, today: date) -> int | None:
    return None if p is None else (today - date.fromtimestamp(p.stat().st_mtime)).days


def read_back(inp: Path, cols_before: list[str], before: list[dict], cells: dict[int, str]) -> str | None:
    """The fault, or None: same row count, the other columns in the same order, every other cell equal, CUSTOMER_ROW exactly as intended."""
    cols, after = read_csv(inp)
    if len(after) != len(before):
        return f"row count changed {len(before)} -> {len(after)}"
    if [c for c in cols if c != COLUMN] != [c for c in cols_before if c != COLUMN] or COLUMN not in cols:
        return "the columns changed (order, name, or the CUSTOMER_ROW column is missing)"
    for i, (b, a) in enumerate(zip(before, after)):
        for k in cols_before:
            if k != COLUMN and (a.get(k) or "") != (b.get(k) or ""):
                return f"row {i + 2}: column {k} changed"
        if (a.get(COLUMN) or "") != cells.get(i, ""):
            return f"row {i + 2}: {COLUMN} is not what was intended"
    return None


def write_column(inp: Path, cells: dict[int, str], today: date | None = None) -> str:
    """Rewrite CUSTOMER_ROW only (cleared first); once-a-day backup; read-back proof; on any fault put the file back and raise."""
    raw = inp.read_bytes()
    cols, rows = read_csv(inp)
    before = [dict(r) for r in rows]
    bak = inp.with_name(inp.stem + ".pre-context.csv")
    if not bak.exists() or date.fromtimestamp(bak.stat().st_mtime) < (today or date.today()):
        shutil.copy2(inp, bak)
    out_cols = cols if COLUMN in cols else [*cols, COLUMN]
    for i, r in enumerate(rows):
        r[COLUMN] = cells.get(i, "")
    try:
        with open(inp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=out_cols, quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(rows)
        fault = read_back(inp, cols, before, cells)
    except Exception as e:                                           # noqa: BLE001
        fault = f"{type(e).__name__}: {e}"
    if fault:
        inp.write_bytes(raw)
        raise RuntimeError(f"read-back proof failed ({fault}); {inp.name} was put back as it was")
    return f"{inp.name}: {len(cells)} row(s) carry {COLUMN}; read-back proof OK; backup {bak.name}"


def load_client_rows(db: Path) -> list[dict]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("select * from client_conferences")]
    finally:
        con.close()


# ------------------------------------------------------------------ the run
def build(markets: list[str], markets_dir: Path, db: Path, today: date) -> dict:
    """{'cells': {market: {i: cell}}, 'inputs': {market: (path, cols, rows)}, 'refused': [...], 'stale': [...], 'from_awards': n}. Writes nothing."""
    from src.cfp_monitor.identity import seed_map
    snaps = Path(markets_dir) / "customer_snapshots"
    res: dict = {"cells": {}, "inputs": {}, "refused": [], "stale": [], "missing": [], "from_awards": 0, "with_contact": 0}
    for m in markets:
        p = Path(markets_dir) / f"{m}_input.csv"
        if not p.exists():
            res["missing"].append(f"{m}: no input list {p.name}, so no context could be built for it")      # FAILED (Codex finding 4)
            continue
        cols, rows = read_csv(p)
        res["inputs"][m] = (p, cols, rows)
    conf = [m for m in markets if m in CONF_MARKETS and m in res["inputs"]]
    if conf:
        for key, folder in CONF_SNAPSHOT_DIRS.items():
            age = copy_age_days(newest_copy(snaps / folder), today)
            if age is None or age > STALE_AFTER_DAYS:
                res["stale"].append(f"{CLIENT_LABEL[key]} conference sheet copy is {'missing' if age is None else f'{age} days old'}")
        cells = conference_cells(load_client_rows(db), {m: res["inputs"][m][2] for m in conf}, seed_map(str(db))[0])
        for m in conf:
            res["cells"][m] = screen({i: c for (mm, i), c in cells.items() if mm == m}, m, res["refused"])
    if "Awards" in res["inputs"]:
        sheets = {}
        for client in AWARD_CLIENTS:
            sp = newest_copy(snaps / client)
            age = copy_age_days(sp, today)
            if age is None or age > STALE_AFTER_DAYS:
                res["stale"].append(f"{CLIENT_LABEL[client]} awards sheet copy is {'missing' if age is None else f'{age} days old'}")
            if sp is not None:
                sheets[client] = read_csv(sp)[1]
        res["cells"]["Awards"] = screen(award_cells(sheets, res["inputs"]["Awards"][2]), "Awards", res["refused"])
        res["from_awards"] = len(res["cells"]["Awards"])
    res["with_contact"] = sum(1 for cells in res["cells"].values() for v in cells.values() if "their coordinator contact:" in v)
    return res


def research_rows(rows: list[dict]) -> list[int]:
    """The rows the audit will actually ask about: not a duplicate, not marked by the refresh plan."""
    return [i for i, r in enumerate(rows) if not (r.get("DUP_OF") or "").strip() and not (r.get("REFRESH_SKIP") or "").strip()]


def _stub_genai() -> None:
    """The rehearsal never calls the API; run_market_audit imports google.genai at load time, which this venv does not carry."""
    try:
        import google.genai  # noqa: F401
        return
    except Exception:                                                # noqa: BLE001
        pass

    class _Any:
        def __getattr__(self, _name):
            return _Any()

        def __call__(self, *a, **k):
            return _Any()

    g = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    gtypes = types.ModuleType("google.genai.types")
    genai.__getattr__ = lambda _n: _Any()                            # type: ignore[attr-defined]
    gtypes.__getattr__ = lambda _n: _Any()                           # type: ignore[attr-defined]
    genai.types = gtypes                                             # type: ignore[attr-defined]
    g.genai = genai                                                  # type: ignore[attr-defined]
    sys.modules.update({"google": g, "google.genai": genai, "google.genai.types": gtypes})


def live_audit_module(markets_dir: Path):
    """The LIVE run_market_audit.py as it is (patched or not), loaded from a temporary copy. Never writes to the Markets folder."""
    return _load_copy((Path(markets_dir) / "run_market_audit.py").read_text(encoding="utf-8"), markets_dir, "rma_live")


def _load_copy(text: str, markets_dir: Path, name: str):
    _stub_genai()
    tmp = Path(tempfile.mkdtemp(prefix="cfp-rehearsal-")) / "run_market_audit.py"
    tmp.write_text(text.replace("\r\n", "\n"), encoding="utf-8")
    if (Path(markets_dir) / "standing_rules.md").exists():
        shutil.copy2(Path(markets_dir) / "standing_rules.md", tmp.parent / "standing_rules.md")
    spec = importlib.util.spec_from_file_location(name, tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def patched_audit_module(markets_dir: Path, patch: Path = PROMPT_PATCH):
    """The LIVE run_market_audit.py with the ACT-72 prompt patch applied IN MEMORY (as is, when the operator has already applied it), loaded
    from a temporary copy. Proves the patch applies to the live script; never writes to the Markets folder."""
    from src.cfp_monitor.unified_patch import apply_unified
    live = (Path(markets_dir) / "run_market_audit.py").read_text(encoding="utf-8")
    text = live.replace("\r\n", "\n") if "customer_block" in live else apply_unified(live, patch.read_text(encoding="utf-8"))
    _stub_genai()
    tmp = Path(tempfile.mkdtemp(prefix="cfp-rehearsal-")) / "run_market_audit.py"
    tmp.write_text(text, encoding="utf-8")
    for extra in ("standing_rules.md", "STANDING_RULES.md"):
        if (Path(markets_dir) / extra).exists():
            shutil.copy2(Path(markets_dir) / extra, tmp.parent / extra)
    spec = importlib.util.spec_from_file_location("rma_rehearsal", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rehearse(res: dict, markets_dir: Path, today: date) -> dict:
    """Every prompt both nights would send, built offline from the patched builder: with the cell and without it. No request is made.
    -> {'prompts', 'with_context', 'avg', 'max', 'total', 'unchanged_without', 'login_hits', 'by_market'}"""
    rma = patched_audit_module(markets_dir)
    live = live_audit_module(markets_dir)
    live_patched = "customer_block" in (Path(markets_dir) / "run_market_audit.py").read_text(encoding="utf-8")
    d = today.isoformat()
    out = {"prompts": 0, "with_context": 0, "growth": [], "unchanged_without": True, "login_hits": 0, "by_market": {}}
    for m, (_p, _cols, rows) in res["inputs"].items():
        build_fn = rma.build_awards_prompt if m == "Awards" else rma.build_conference_prompt
        live_fn = live.build_awards_prompt if m == "Awards" else live.build_conference_prompt
        cells = res["cells"].get(m, {})
        n = k = 0
        for i in research_rows(rows):
            base_row = {kk: v for kk, v in rows[i].items() if kk != COLUMN}
            base = build_fn(dict(base_row), d)
            blank = build_fn({**base_row, COLUMN: ""}, d)
            # The patched builder against the LIVE unpatched one (Codex finding 5), and absent against blank. When the operator has already
            # applied the patch the live builder is the patched one, so only absent-versus-blank can still be checked here.
            out["unchanged_without"] &= (base == blank) and (live_patched or base == live_fn(dict(base_row), d))
            n += 1
            if i in cells:
                with_ctx = build_fn({**base_row, COLUMN: cells[i]}, d)
                out["growth"].append(len(with_ctx) - len(base))
                out["login_hits"] += bool(LOGIN_PATTERN.search(with_ctx))
                k += 1
        out["by_market"][m] = {"prompts": n, "with_context": k}
        out["prompts"] += n
        out["with_context"] += k
    g = out.pop("growth")
    out.update(avg=round(sum(g) / len(g)) if g else 0, max=max(g, default=0), total=sum(g))
    return out


def evidence_dir(today: date) -> Path:
    from src.cfp_monitor.qa_report import QA_ROOT, cycle_of
    return QA_ROOT / cycle_of(today).isoformat()


def write_evidence(res: dict, today: date, out_dir: Path | None = None) -> Path:
    d = Path(out_dir) if out_dir else evidence_dir(today)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "customer_context.csv"
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["market", "row", "EVENT_ID_CANON", "CONFERENCE", "chars"])
        for m, cells in res["cells"].items():
            rows = res["inputs"][m][2]
            for i, c in sorted(cells.items()):
                w.writerow([m, i + 2, rows[i].get("EVENT_ID_CANON", ""), rows[i].get("CONFERENCE", ""), len(c)])
    with open(d / "customer_context_refused.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["market", "row", "why"])
        w.writeheader()
        w.writerows(res["refused"])
    return p


def verdict_line(res: dict, rehearsal: dict | None, failed: list[str], evidence: Path | None) -> tuple[str, int]:
    n = sum(len(c) for c in res["cells"].values())
    m = sum(len(research_rows(rows)) for (_p, _c, rows) in res["inputs"].values())
    on = sum(1 for mk, cells in res["cells"].items() for i in cells if i in set(research_rows(res["inputs"][mk][2])))
    failed = [*res.get("missing", []), *failed]
    status, code = ("FAILED", 1) if failed else (("DEGRADED", 2) if res["stale"] or res["refused"] else ("HEALTHY", 0))
    line = (f"CUSTOMER CONTEXT: {status} - {on} of {m} research rows carry the customer's row ({n} input rows in all, "
            f"{res['from_awards']} from awards sheets, {res.get('with_contact', 0)} with a coordinator contact); "
            f"{len(res['refused'])} cell(s) dropped for a login or password pattern")
    if rehearsal:
        line += (f"; REHEARSAL {rehearsal['prompts']} prompts built offline, {rehearsal['with_context']} with context, growth about "
                 f"{rehearsal['avg']} chars (max {rehearsal['max']}, {rehearsal['total']} in all), a row without context gets "
                 f"{'the same prompt as before' if rehearsal['unchanged_without'] else 'a DIFFERENT prompt (fault)'}, "
                 f"{rehearsal['login_hits']} login or password pattern(s) in any prompt")
    if res["stale"]:
        line += "; " + "; ".join(res["stale"])
    if failed:
        line += "; " + "; ".join(failed)
    if evidence:
        line += f"; evidence {evidence}"
    return line, code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markets", default="Cybersecurity,Utility", help="comma list of Awards, Cybersecurity, Utility")
    ap.add_argument("--markets-dir", default=str(MARKETS))
    ap.add_argument("--db", default=str(LIVE_DB))
    ap.add_argument("--today", default=date.today().isoformat())
    ap.add_argument("--apply", action="store_true", help="write the CUSTOMER_ROW column (otherwise report only)")
    ap.add_argument("--clear", action="store_true", help="the switch is off: empty the CUSTOMER_ROW column of these markets")
    ap.add_argument("--rehearse", action="store_true", help="build every prompt of both nights offline (no request); writes only evidence")
    ap.add_argument("--evidence-dir", default="", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                # noqa: BLE001
        pass
    today = date.fromisoformat(a.today)
    markets = list(ALL_MARKETS) if a.rehearse else [m.strip() for m in a.markets.split(",") if m.strip()]
    if a.clear:
        done = []
        for m in markets:
            p = Path(a.markets_dir) / f"{m}_input.csv"
            try:
                if p.exists() and COLUMN in read_csv(p)[0]:
                    done.append(write_column(p, {}, today))
            except Exception as e:                                   # noqa: BLE001
                print(f"CUSTOMER CONTEXT: FAILED - {m}: {e}")
                return 1
        print("CUSTOMER CONTEXT: OFF - the switch is off; " + ("; ".join(done) if done else "no research list carried the column"))
        return 0
    try:
        res = build(markets, Path(a.markets_dir), Path(a.db), today)
    except Exception as e:                                           # noqa: BLE001  never a reason to stop the research
        print(f"CUSTOMER CONTEXT: FAILED - the context could not be built ({type(e).__name__}: {e}); the research lists were not changed")
        return 1
    rehearsal = None
    if a.rehearse:
        try:
            rehearsal = rehearse(res, Path(a.markets_dir), today)
        except Exception as e:                                       # noqa: BLE001
            print(f"CUSTOMER CONTEXT: FAILED - the rehearsal did not run ({type(e).__name__}: {e})")
            return 1
    failed = []
    if a.apply and not a.rehearse:
        for m, cells in res["cells"].items():
            try:
                print("  " + write_column(res["inputs"][m][0], cells, today))
            except Exception as e:                                   # noqa: BLE001
                failed.append(f"{m}: {e}")
    try:
        ev = write_evidence(res, today, Path(a.evidence_dir) if a.evidence_dir else None)
    except Exception as e:                                           # noqa: BLE001
        ev = None
        print(f"  (evidence not written: {type(e).__name__}: {e})")
    line, code = verdict_line(res, rehearsal, failed, ev)
    print(line)
    if not a.apply:
        print("  report only: the research lists were not changed" + ("" if a.rehearse else " (add --apply)"))
    if rehearsal:
        print("  by market: " + "; ".join(f"{m} {v['with_context']} of {v['prompts']} prompts" for m, v in rehearsal["by_market"].items()))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
