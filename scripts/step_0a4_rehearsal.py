"""Does step 0a4 of run_monthly.ps1 (the customer context) actually RUN? Run the REAL block on scratch copies and read what it prints.

    python scripts/step_0a4_rehearsal.py --kind friday        # the awards night's shape: $Markets = Awards
    python scripts/step_0a4_rehearsal.py --kind saturday      # the conference night's shape: Cybersecurity and Utility
    python scripts/step_0a4_rehearsal.py --lint-only          # the static check only (no PowerShell run)

WHY (plan step 1.20, Matt 2026-11-13: "next week I expect this will not happen again"). On Friday 2026-11-13 step 0a4 crashed (a one-element array
splatted as characters: `- - a p p l y`) and the awards research ran with no customer context. Every check before that was a check of the TEXT (a hash, a
dry run, the Thursday pre-flight's STEP-marker test, a Codex read): nobody RAN the step. This runs it: the block is cut out of the LIVE script, its three
paths are pointed at scratch (a copy of the research lists, the sheet copies and the database; shims for the two cfp-monitor scripts it calls; a stub in
place of the held-notice email), and it is run by Windows PowerShell exactly as the night run would, with the real interpreter and the real arguments.

VERDICT (one line, last): STEP 0A4 REHEARSAL: GREEN | YELLOW | RED - ... Exit 0 GREEN / 2 YELLOW / 1 RED (also when the rehearsal itself could not run).
  RED    a usage error, no CUSTOMER CONTEXT line, FAILED, UNKNOWN, zero research rows carrying the customer's row, or the block's own hold fired:
         tonight's research would run WITHOUT context (or be held, with patch ACT-76). The same test ACT-76 and the 03:00 check use.
  YELLOW DEGRADED with rows (a dropped cell, an old copy): the research runs with context.
  GREEN  HEALTHY (or OFF: the switch CFP_CUSTOMER_CONTEXT=0 is on).
A static lint runs with it: a variable built by an if / switch / foreach expression and then splatted (`@name`) is the trap that caused the crash.

Nothing live is changed: the lists, snapshots and database are COPIED to a temp folder (deleted afterwards, it holds customer text), the block runs
against that, and no email is sent. Evidence (counts and the verdict line, no cell text) goes to runs_out/qa/<date>/step_0a4_rehearsal_<time>.json."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import customer_sheet_load as csl      # noqa: E402  (context_level: the one allowlist for a CUSTOMER CONTEXT line)

MARKETS =Path(os.environ.get("CFP_MARKETS_DIR") or Path.home() / "Desktop" / "Nicolia-PR-Prime" / "Markets")
LIVE_RM = MARKETS / "run_monthly.ps1"
LOCAL = Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor"
LIVE_DB = LOCAL / "cfp_monitor.db"
QA_ROOT = LOCAL / "runs_out" / "qa"
POWERSHELL = shutil.which("powershell") or "powershell.exe"
TIMEOUT_S = 600

# The block's own literals (the live script hard-codes them). Each is replaced by a scratch path or a stub for the rehearsal.
WRITER = r"C:\Users\matts\cfp-monitor\scripts\customer_row_context.py"
ANSWERS = r"C:\Users\matts\cfp-monitor\scripts\customer_row_answers.py"
NOTICE = r"C:\Users\matts\cfp-monitor\scripts\customer_sheet_load.py"

SHAPES = {
    "friday": "$Markets = @('Awards'); $liveMarkets = @()",
    "saturday": "$Markets = @('Cybersecurity','Utility'); $liveMarkets = @('Cybersecurity','Utility')",
}
START = "if (($liveMarkets.Count -gt 0 -or $Markets -contains 'Awards') -and -not $WhatIf) {"
PY_PATH = re.compile(r"[A-Za-z]:\\[^\"'\s)]+?\.py", re.I)


def extract_block(text: str) -> str:
    """The step 0a4 block of run_monthly.ps1: from its `if` (after the STEP 0a4 marker) to just before the STEP 0b marker. Raises ValueError when absent."""
    m = text.find("STEP 0a4: CUSTOMER CONTEXT")
    if m < 0:
        raise ValueError("the script has no STEP 0a4 marker (patch ACT-72 is not applied)")
    a = text.find(START, m)
    b = text.find("STEP 0b: CANARY", m)
    if a < 0 or b < a:
        raise ValueError("could not find the step 0a4 block between its marker and STEP 0b")
    end = text.rfind("\n", a, b)
    return text[a:end if end > a else b]


def lint_splat(text: str) -> list[str]:
    """Variables built by an if / switch / foreach expression and then splatted with @name. PowerShell unrolls a one-element array returned by such an
    expression into a plain string, and a splatted string is passed one character at a time (the 2026-11-13 crash)."""
    out = []
    for m in re.finditer(r"(?m)^\s*\$(\w+)\s*=\s*(?:if|switch|foreach)\b", text):
        var = m.group(1)
        if re.search(r"(?<![\w$])@" + re.escape(var) + r"\b", text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(f"line {line}: ${var} is built by an if/switch/foreach expression and then splatted as @{var}: wrap the expression in @( )")
    return out


def classify(output: str, returncode: int) -> tuple[str, str, str | None]:
    """(GREEN|YELLOW|RED, reason, the CUSTOMER CONTEXT line) from the block's output and process exit code. The verdict line itself is judged by
    customer_sheet_load.context_level, an allowlist shared with the 03:00 watch (Codex review 2026-11-13: an unrecognised verdict word used to be GREEN)."""
    lines = re.findall(r"^CUSTOMER CONTEXT: (.+)$", output, flags=re.M)
    line = lines[-1].strip() if lines else None
    usage = re.search(r"(?m)^usage: |unrecognized arguments|the following arguments are required", output)
    if usage:
        return "RED", "the writer was started with arguments it does not accept (a usage error): " + (usage.group(0) or "").strip(), line
    if "RESEARCH HELD (ACT-76)" in output or returncode == 6:
        return "RED", "the block's own hold fired: the context did not build", line
    level, reason = csl.context_level(line)
    if level == "GREEN" and line and line.startswith("OFF"):
        reason = "the context is switched off (CFP_CUSTOMER_CONTEXT=0)"
    return level, reason, line


def _writer_shim(extra: list[str], work: Path) -> Path:
    """A python file that runs the REAL customer_row_context.main with the block's own arguments plus the scratch paths."""
    p = work / "writer_shim.py"
    p.write_text(f"import sys\nsys.path.insert(0, {str(HERE)!r})\nimport customer_row_context as m\nraise SystemExit(m.main(sys.argv[1:] + {extra!r}))\n", encoding="ascii")
    return p


def rehearse(kind: str, markets: Path | None = None, db: Path | None = None, run=None) -> dict:
    """Run the live step 0a4 block on scratch copies. Returns {'verdict', 'reason', 'line', 'exit', 'lint', 'seconds'}. Never raises; always cleans up."""
    markets, db = Path(markets or MARKETS), Path(db or LIVE_DB)
    started = datetime.now()
    res = {"kind": kind, "verdict": "RED", "reason": "", "line": None, "exit": None, "lint": [], "seconds": 0, "at": started.isoformat(timespec="seconds")}
    work = Path(tempfile.mkdtemp(prefix="step0a4_"))
    try:
        text = (markets / "run_monthly.ps1").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        res["lint"] = lint_splat(text)
        block = extract_block(text)
        scratch = work / "markets"
        scratch.mkdir()
        for f in markets.glob("*_input.csv"):
            shutil.copy2(f, scratch / f.name)
        if (markets / "customer_snapshots").is_dir():
            shutil.copytree(markets / "customer_snapshots", scratch / "customer_snapshots")
        dbcopy = work / "db.sqlite"
        shutil.copy2(db, dbcopy)
        ev = work / "evidence"
        ev.mkdir()
        writer = _writer_shim(["--markets-dir", str(scratch), "--db", str(dbcopy), "--evidence-dir", str(ev)], work)
        answers = work / "answers_shim.py"
        answers.write_text(f"import sys\nsys.path.insert(0, {str(HERE)!r})\nimport customer_row_answers as a\n"
                           f"sys.argv = [sys.argv[0], '--markets-dir', {str(scratch)!r}, '--db', {str(dbcopy)!r}, '--out-dir', {str(ev)!r}]\nraise SystemExit(a.main())\n", encoding="ascii")
        notice = work / "notice_stub.py"
        notice.write_text("print('HELD NOTICE (rehearsal): no email is sent from a rehearsal')\n", encoding="ascii")
        if WRITER not in block:
            raise ValueError("unsafe to rehearse: the block does not call the writer by the path this rehearsal expects, so it cannot be redirected to scratch")
        block = block.replace(WRITER, str(writer)).replace(ANSWERS, str(answers)).replace(NOTICE, str(notice))
        # Codex review 2026-11-13: the replacement used to be unchecked. If the live block ever names another script path, the harness would run THAT, against the live
        # lists and database, or send a real email. So: every script path left in the block must be one of the scratch shims, or nothing is run.
        live_left = [p for p in PY_PATH.findall(block) if not p.lower().startswith(str(work).lower())]
        if live_left:
            raise ValueError("unsafe to rehearse: the block still names a script that is not a scratch shim (" + "; ".join(sorted(set(live_left))[:3]) + "): refusing to run it")
        harness = work / "harness.ps1"
        harness.write_text("$WhatIf = $false\r\n" + SHAPES[kind] + "\r\n" + block + "\r\nWrite-Host 'REHEARSAL-CONTINUED'\r\n", encoding="utf-8")
        cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)]
        r = (run or subprocess.run)(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        res["exit"] = r.returncode
        res["verdict"], res["reason"], res["line"] = classify(out, r.returncode)
    except subprocess.TimeoutExpired:
        res["reason"] = f"the step did not finish in {TIMEOUT_S} seconds"
    except Exception as exc:                                                  # noqa: BLE001
        res["verdict"], res["reason"] = "RED", f"the rehearsal could not run: {type(exc).__name__}: {exc}"
        res["could_not_run"] = True
    finally:
        shutil.rmtree(work, ignore_errors=True)                                # it held copies of the customer's text
        if work.exists():
            res["leftover"] = str(work)
    if res.get("leftover"):
        res["reason"] += f"; WARNING: the scratch folder {res['leftover']} could not be deleted: delete it by hand (it holds copies of the customer's text)"
        if res["verdict"] == "GREEN":
            res["verdict"] = "YELLOW"
    if res["lint"] and res["verdict"] == "GREEN":
        res["verdict"], res["reason"] = "YELLOW", "the step ran, but the lint found a splat trap: " + "; ".join(res["lint"])
    res["seconds"] = round((datetime.now() - started).total_seconds(), 1)
    return res


def write_evidence(res: dict, qa_root: Path | None = None) -> Path | None:
    try:
        now = datetime.now()
        d = Path(qa_root or QA_ROOT) / now.strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"step_0a4_rehearsal_{now.strftime('%H%M%S')}.json"
        p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        return p
    except Exception:                                                         # noqa: BLE001
        return None


def verdict_line(res: dict, evidence: Path | None = None) -> str:
    extra = f"; evidence: {evidence}" if evidence else ""
    return f"STEP 0A4 REHEARSAL: {res['verdict']} - {res['reason']} ({res.get('kind')} shape, {res.get('seconds', 0)} s){extra}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=sorted(SHAPES), default="saturday")
    ap.add_argument("--lint-only", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                         # noqa: BLE001
        pass
    if a.lint_only:
        found = lint_splat(LIVE_RM.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n"))
        print("\n".join(f"  - {f}" for f in found))
        print(f"STEP 0A4 LINT: {'RED - ' + str(len(found)) + ' splat trap(s)' if found else 'GREEN - no variable is built by an if-expression and then splatted'}")
        return 1 if found else 0
    res = rehearse(a.kind)
    ev = write_evidence(res)
    print(verdict_line(res, ev))
    return {"GREEN": 0, "YELLOW": 2}.get(res["verdict"], 1)


if __name__ == "__main__":
    sys.exit(main())
