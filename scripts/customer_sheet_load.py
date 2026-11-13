"""The customer sheets must load before the research. Retry, then ONE plain email that says what broke and how to fix it.

    python scripts/customer_sheet_load.py --clients all --context saturday       # fetch + copy, 3 tries over 15 min, CRITICAL email, then wait up to 2 h
    python scripts/customer_sheet_load.py --clients arnica-awards,utility-awards --context friday
    python scripts/customer_sheet_load.py --clients all --once                   # the person's re-run: one try, no email, prints the verdict
    python scripts/customer_sheet_load.py --deadman auto                         # fetches NOTHING: are today's copies there? (03:00 Fri and Sat task)
    python scripts/customer_sheet_load.py --check-only                           # read-only: can every sheet be read right now? (Thursday)
    python scripts/customer_sheet_load.py --test-send                            # one "[TEST] ..." email with a sample body

WHY (Matt, 2026-11-09, in chat): "if the customer sheets don't load I need immediate emergency escalation so that they load - this is an
absolutely foundational step that needs to send me a clear simple alert if it fails like CFP customer sheets failed to load - critical error
(then direct me how to fix it)". Until then a failed load wrote a Desktop file and reached him only inside the end-of-run recap, hours later.

WHAT COUNTS AS A FAILURE: a sheet that does not download, comes back empty or with the wrong shape (fetch_customer_sheet.validate), or whose
copy is older than this run (the fetch said yes but no new file landed in customer_snapshots/<client>/).

RETRIES: a failure that can clear by itself (network, Google down, an error we do not recognise, a copy not saved) is tried 3 times over about
15 minutes (now, +5 min, +15 min). A failure a retry cannot fix (key missing or invalid, sharing removed, sheet layout changed, a library
missing, the settings file missing) is not retried: waiting 15 minutes to say the same thing helps nobody.

THE EMAIL goes to CFP_RECAP_TO through alerts.maybe_send_email, at most once a day (a second failure the same day, or the 03:00 dead-man
check after the run already alerted, does not send again). Subject, exactly: "CFP customer sheets failed to load - CRITICAL ERROR". The same
text is written to the Desktop file (fetch_customer_sheet.alert_paths) and the evidence (every attempt's output, the outcome per sheet) to
runs_out/qa/<date>/sheet_load_<time>.json, named in the verdict line. No secret value is ever written: the key file is named by its path only,
and redact() strips any secret-looking environment value or private-key block before anything is written or sent.

THE WAIT (Matt, 2026-11-10, asked how long the research should wait for the sheets: "Wait up to 2 hours"). After the CRITICAL email the
load keeps trying every 10 minutes, for up to 2 hours from the first failure (CFP_SHEETS_HOLD_HOURS, default 2; 0 = no wait). If the sheets
load, the research starts by itself on the fresh copies and a second email says so: "CFP customer sheets loaded - research started". The wait
is cut short to fit the research task's own time limit (Windows stops a task at its limit), so waiting never cuts the research off.

THE HOLD (Matt, 2026-11-13, D66 = B: "If the customer sheets don't load I do NOT want to proceed - this is the first and most critical step and
foundational to data success"). If the sheets still do not load when the wait ends, the research does NOT start: this exits 6 (HELD), run_monthly.ps1
(patch ACT-75) ends right there before the archive, the canary and any spend, and a second email says so ("CFP research HELD - customer sheets
still not loaded - CRITICAL ERROR") with the commands to re-run just the sheet load and to start the research once it works. There is no automatic
restart: Matt starts the task (Start-ScheduledTask). The weekend shows as HELD in the recap and the Sunday gate (runs_out/sheet_load_status.json).
CFP_SHEETS_ON_FAIL=proceed, set by a person starting run_monthly.ps1 by hand, brings back the 11-10 rule: the research goes ahead on the last good
copies, exit 1, DEGRADED. It is never the default.

THE 03:00 CHECK (--deadman) tells three cases apart: the research task did not start today (CRITICAL email, with how to start it by hand);
the task is running but the sheets have not loaded yet (no email: the run alerts and waits by itself); the task ran and today's copies are
missing (CRITICAL email, cause read from today's run log).

Exit codes: 0 HEALTHY (also when the sheets loaded during the wait, or the 03:00 check found the run still going), 1 FAILED (the person's --once
re-run, the 03:00 check, or CFP_SHEETS_ON_FAIL=proceed: the research goes ahead on old copies), 2 the check itself failed, 6 HELD (the sheets did not
load: the research must NOT start).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import fetch_customer_sheet as fcs                                           # noqa: E402

PY = sys.executable
FETCH = HERE / "fetch_customer_sheet.py"
THIS = Path(__file__).resolve()
LOCAL = Path(os.environ.get("LOCALAPPDATA", ".")) / "CFP-Monitor"
CONFIG = LOCAL / "customer_sheets.json"
RUNS_OUT = LOCAL / "runs_out"
QA_ROOT = RUNS_OUT / "qa"
SENT_STATE = RUNS_OUT / "sheet_alert_sent.json"
STATUS = RUNS_OUT / "sheet_load_status.json"          # the last load per research (friday / saturday): read by the recap and the Sunday gate
MARKETS = Path(os.environ.get("CFP_MARKETS_DIR") or Path.home() / "Desktop" / "Nicolia-PR-Prime" / "Markets")
SNAPSHOTS = MARKETS / "customer_snapshots"
LOGS = MARKETS / "logs"

SUBJECT = "CFP customer sheets failed to load - CRITICAL ERROR"
SUBJECT_LOADED = "CFP customer sheets loaded - research started"
SUBJECT_STILL = "CFP customer sheets still not loaded - research ran on copies from {copies}"       # only with CFP_SHEETS_ON_FAIL=proceed (the 11-10 rule)
SUBJECT_HELD = "CFP research HELD - customer sheets still not loaded - CRITICAL ERROR"
SUBJECT_CONTEXT_HELD = "CFP research HELD - customer context did not build - CRITICAL ERROR"
# Matt, 2026-11-13 (D66 = B): "If the customer sheets don't load I do NOT want to proceed - this is the first and most critical step and
# foundational to data success." So after the retries, the CRITICAL email and the wait, a research that cannot get its sheets does NOT start:
# exit 6, nothing researched, nothing spent. Matt starts it by hand once the sheets load. CFP_SHEETS_ON_FAIL=proceed brings the 11-10 rule back
# (research on the last good copies, DEGRADED); it is for a person starting run_monthly.ps1 by hand, never the default.
HELD_EXIT = 6
ON_FAIL_VAR = "CFP_SHEETS_ON_FAIL"
HOLD_VAR = "CFP_SHEETS_HOLD_HOURS"
# Matt, 2026-11-10 (asked how long the research should wait when the customer sheets do not load): "Wait up to 2 hours".
HOLD_DEFAULT_H = 2.0
HOLD_MAX_H = 4.0                         # a typo of 20 must not hold a research run past its task limit
HOLD_POLL_S = 600                        # one try every 10 minutes while waiting
# Hours each research needs AFTER the sheets (its slowest recent runs, rounded up: Friday 10.8 h on 11-06, Saturday 4.5 h). The wait is cut
# so that this still fits inside the task's own time limit (Friday 16 h; Saturday 5 h, 8 h once Matt raises it, D14).
RESEARCH_NEEDS_H = {"friday": 11.5, "saturday": 5.0}
HOLD_MARGIN_H = 0.25
WAITS = (300, 600)                       # tries at 0, +5 and +15 minutes
FETCH_TIMEOUT = 600
DEADMAN_START_GRACE_S = 5 * 60           # the PC woke for the 03:00 check: a research task that missed 02:00 starts within a minute or two
DEADMAN_POLL_S = 30

ALL_CLIENTS = ("arnica", "utility", "arnica-awards", "utility-awards")
AWARD_CLIENTS = ("arnica-awards", "utility-awards")
LABELS = {"arnica": "Arnica conferences sheet", "utility": "Utility Global conferences sheet",
          "arnica-awards": "Arnica awards sheet", "utility-awards": "Utility Global awards sheet"}
CONTEXTS = {
    "friday": ("the Friday 02:00 awards research", "CFP Weekly Awards Research", AWARD_CLIENTS),
    "saturday": ("the Saturday 02:00 conference research", "CFP Weekly Re-Research (live markets)", ALL_CLIENTS),
}

# ------------------------------------------------------------------------------------------------ causes
# Matched against the fetch's own error text, in this order. Each cause names what Matt does himself and what the re-run does for him.
RULES = (
    ("software", ("No module named",)),
    ("config", ("No config at", "config unreadable", "Unknown client", "KeyError: 'service_account_key'", "JSONDecodeError")),
    ("key", ("Service account key not found", "invalid_grant", "invalid_client", "Invalid JWT", "account not found")),
    ("sharing", ("404 from the export endpoint", "401 from the export endpoint", "403 from the export endpoint", "HTML page, not CSV")),
    ("structure", ("is missing column(s)", "has no rows", "carries none of", "unknown sheet kind", "header cell")),
    ("network", ("timed out", "Timeout", "TransportError", "ConnectionError", "Connection aborted", "Connection reset", "Max retries exceeded",
                 "NameResolution", "getaddrinfo", "name resolution", "Server Error", "429", "SSLError", "RemoteDisconnected", "Network is unreachable")),
    ("key", ("RefreshError", "MalformedError", "private key", "DefaultCredentialsError")),
)
RETRYABLE = {"network", "unknown", "not_saved"}


def classify(reason: str) -> str:
    for cause, needles in RULES:
        if any(n in reason for n in needles):
            return cause
    return "unknown"


# ------------------------------------------------------------------------------------------------ plumbing
def run(cmd: list, timeout: int = FETCH_TIMEOUT) -> tuple[int, str]:
    """Run a step. Never raises."""
    try:
        p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except Exception as exc:                                                  # noqa: BLE001
        return 125, f"{type(exc).__name__}: {exc}"


SECRET_NAME = re.compile(r"(PASS|PASSWORD|KEY|TOKEN|SECRET)", re.I)
# A whole block, or a BEGIN with its END cut off (an error text truncated to 300 characters must not leak the start of a key).
PRIVATE_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*\Z)", re.S)


def redact(text: str, env: dict | None = None) -> str:
    """Strip every secret-looking environment value (names with PASS, KEY, TOKEN or SECRET, 8 characters or more) and any private-key block."""
    env = os.environ if env is None else env
    text = PRIVATE_BLOCK.sub("[private key removed]", text)
    for name, value in env.items():
        if value and len(value) >= 8 and SECRET_NAME.search(name) and value in text:
            text = text.replace(value, f"[{name} removed]")
    return text


def config_info(config: Path) -> dict:
    """{'ok', 'key', 'clients': {name: {'kind', 'url'}}, 'error'}. Reads the settings file; never opens the key file."""
    try:
        cfg = json.loads(Path(config).read_text(encoding="utf-8-sig"))
        clients = {}
        for name, e in (cfg.get("clients") or {}).items():
            url = f"https://docs.google.com/spreadsheets/d/{e.get('sheet_id', '')}/edit#gid={e.get('gid', '')}" if e.get("sheet_id") else ""
            clients[name] = {"kind": e.get("kind", fcs.DEFAULT_KIND), "url": url}
        return {"ok": True, "key": str(cfg.get("service_account_key", "")), "clients": clients, "error": ""}
    except Exception as exc:                                                  # noqa: BLE001
        return {"ok": False, "key": "", "clients": {}, "error": f"config unreadable ({type(exc).__name__}) - {config}"}


def taken_at(path: Path | None) -> datetime | None:
    m = re.search(r"_(\d{8}-\d{6})\.csv$", path.name) if path else None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else None
    except ValueError:
        return None


def newest_copy(client: str, snapshots: Path) -> Path | None:
    d = Path(snapshots) / client
    files = sorted(d.glob(f"{client}_*.csv")) if d.is_dir() else []
    return files[-1] if files else None


def expand(clients, config: Path) -> list[str]:
    if isinstance(clients, (list, tuple)):
        return list(clients)
    if clients == "all":
        names = list(config_info(config)["clients"])
        return names or list(ALL_CLIENTS)
    return [c.strip() for c in clients.split(",") if c.strip()]


def parse_duration_h(text: str | None) -> float | None:
    """'PT5H' -> 5.0, 'PT45M' -> 0.75, 'P3D' -> 72.0. None for no limit ('PT0S', blank) or anything unreadable."""
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", (text or "").strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, se = (int(g or 0) for g in m.groups())
    hours = d * 24 + h + mi / 60 + se / 3600
    return hours or None


def task_info(task: str, runner=None) -> dict:
    """{'state', 'last_run', 'limit_h'} of a scheduled task, READ ONLY (Get-ScheduledTask). {} when it cannot be read. Never raises."""
    q = task.replace("'", "''")
    cmd = ("$t = Get-ScheduledTask -TaskName '" + q + "' -ErrorAction Stop; $i = Get-ScheduledTaskInfo -TaskName '" + q + "'; "
           "[pscustomobject]@{state = [string]$t.State; last = $i.LastRunTime.ToString('s'); limit = [string]$t.Settings.ExecutionTimeLimit} "
           "| ConvertTo-Json -Compress")
    code, out = (runner or run)(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd], timeout=60)
    try:
        d = json.loads([ln for ln in (out or "").splitlines() if ln.strip().startswith("{")][-1])
        last = datetime.fromisoformat(d["last"]) if d.get("last") else None
        return {"state": str(d.get("state") or ""), "last_run": last, "limit_h": parse_duration_h(d.get("limit"))}
    except Exception:                                                         # noqa: BLE001
        return {}


def fmt_h(hours: float) -> str:
    mins = int(round(hours * 60))
    return f"{mins} minutes" if mins < 120 or mins % 60 else f"{mins // 60} hours"


def hold_plan(context: str | None, env: dict | None = None, task_reader=None) -> tuple[float, str]:
    """(hours to wait for the sheets, why it is shorter than asked or ''). Never raises."""
    raw = ((os.environ if env is None else env).get(HOLD_VAR) or "").strip()
    note = ""
    try:
        want = float(raw) if raw else HOLD_DEFAULT_H
    except ValueError:
        want, note = HOLD_DEFAULT_H, f"{HOLD_VAR}={raw!r} is not a number, so the usual {HOLD_DEFAULT_H:g} hours is used"
    want = max(0.0, min(want, HOLD_MAX_H))
    if want == 0:
        return 0.0, f"{HOLD_VAR} is 0 (no wait)"
    if context not in CONTEXTS:
        return want, note
    task = CONTEXTS[context][1]
    try:
        limit = (task_reader or task_info)(task).get("limit_h")
    except Exception:                                                         # noqa: BLE001
        limit = None
    if not limit:
        return want, note
    room = limit - RESEARCH_NEEDS_H[context] - HOLD_MARGIN_H
    if room >= want:
        return want, note
    room = max(0.0, round(room, 2))
    return room, (f"Windows stops '{task}' after {limit:g} hours and the research itself needs about {RESEARCH_NEEDS_H[context]:g}, "
                  f"so a longer wait would cut it off" + (" (raise the task's limit to allow the full wait)" if room < want else ""))


HOLD_MARKER = "RESEARCH HELD (ACT-75)"


def hold_wired(markets: Path | None = None) -> bool:
    """True when the live run_monthly.ps1 carries patch ACT-75, the part that actually STOPS the run at exit 6. These scripts are live the moment they are
    saved, the patch only when Matt applies it: until then a HELD email would promise 'the research did NOT start' while it runs. So until the patch is
    in (or the file cannot be read) a failed load behaves as it did from 2026-11-10 to 2026-11-13: exit 1, the research goes ahead, DEGRADED."""
    try:
        return HOLD_MARKER in (Path(markets or MARKETS) / "run_monthly.ps1").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def on_fail_mode(env: dict | None = None) -> str:
    """'hold' (Matt 2026-11-13: do NOT proceed when the sheets do not load) or 'proceed' (the 2026-11-10 rule). CFP_SHEETS_ON_FAIL=proceed or =hold
    forces either, by hand; otherwise it is 'hold' exactly when the live run script can enforce it (patch ACT-75 applied)."""
    raw = ((os.environ if env is None else env).get(ON_FAIL_VAR) or "").strip().lower()
    if raw in ("proceed", "hold"):
        return raw
    return "hold" if hold_wired() else "proceed"


def research_markets(context: str | None) -> str:
    return "Awards" if context == "friday" else "Cybersecurity,Utility"


def start_research_command(context: str | None) -> str:
    """The line that starts the held research once the sheets load: the same task Task Scheduler starts at 02:00."""
    task = CONTEXTS.get(context or "", (None, None, None))[1]
    return f"Start-ScheduledTask -TaskName '{task}'" if task else "Start-ScheduledTask -TaskName '<the research task>'"


def proceed_command(context: str | None) -> str:
    """The last resort, by hand: the same run as the task, told to go ahead on the old copies if the sheets still do not load."""
    return (f"$env:{ON_FAIL_VAR} = 'proceed'; & {ps(MARKETS / 'run_monthly.ps1')} -Markets {research_markets(context)}")


def held_steps(context: str | None) -> list[str]:
    """THEN START THE RESEARCH: what Matt does after the fix. Plain, exact commands."""
    what = CONTEXTS.get(context or "", ("the research", None, None))[0]
    return ["THEN START THE RESEARCH (it is held; it will not start by itself again)",
            "1. Confirm the sheets load now. This tries each failed sheet once, saves a fresh copy and prints SHEET LOAD: HEALTHY, or the reason it still fails.",
            "   The re-run command is in the numbered steps above.",
            f"2. When it says SHEET LOAD: HEALTHY, start {what}: it is the normal full job, from its own start (its time limit starts again, and its own sheet load runs first):",
            f"       {start_research_command(context)}",
            "3. Only if you decide to research on the OLD copies instead (the old rule, your choice, by hand): in PowerShell, run",
            f"       {proceed_command(context)}",
            "   Anything the customer changed since the last good copy is then not seen this week, and the recap and the Sunday check show DEGRADED.",
            ""]


# ------------------------------------------------------------------------------------------------ one attempt, then the retries
def parse_attempt(output: str, code: int, clients: list[str], started: datetime, snapshots: Path, check_fresh: bool = True) -> dict:
    """{client: {'ok', 'reason', 'cause', 'copy', 'rows'}} from one run of fetch_customer_sheet.py."""
    lines = [ln.strip() for ln in redact(output or "").splitlines() if ln.strip()]       # redacted BEFORE any reason is cut or stored
    general = [ln for ln in lines if not any(ln.startswith(f"{c}:") for c in clients) and not ln.startswith(("alert written:", "Traceback"))]
    general_reason = general[-1] if general else f"the fetch exited {code} and printed nothing"
    start = started.replace(microsecond=0)
    out = {}
    for c in clients:
        fail = next((ln for ln in lines if ln.startswith(f"{c}: FAILED - ")), None)
        got = next((ln for ln in lines if ln.startswith(f"{c}: fetched ")), None)
        if fail:
            reason = fail.split(": FAILED - ", 1)[1]
            out[c] = {"ok": False, "reason": reason, "cause": classify(reason), "copy": None, "rows": None}
        elif got:
            m = re.search(r"fetched (\d+) rows", got)
            rows = int(m.group(1)) if m else None
            copy = newest_copy(c, snapshots)
            if check_fresh and not (copy and taken_at(copy) and taken_at(copy) >= start):
                out[c] = {"ok": False, "reason": "the sheet downloaded but no new copy was saved in " + str(Path(snapshots) / c)
                          + (f" (newest is {copy.name})" if copy else " (there is no copy at all)"), "cause": "not_saved", "copy": None, "rows": rows}
            else:
                out[c] = {"ok": True, "reason": "", "cause": None, "copy": str(copy) if (copy and check_fresh) else None, "rows": rows}
        else:
            out[c] = {"ok": False, "reason": general_reason, "cause": classify(general_reason), "copy": None, "rows": None}
    return out


def load(clients: list[str], config: Path, snapshots: Path, waits=WAITS, sleep=time.sleep, runner=None, now=datetime.now,
         read_only: bool = False) -> dict:
    """Fetch (and copy, unless read_only) every client; retry only what can clear by itself. Never raises."""
    runner = runner or run
    outcomes: dict = {}
    attempts: list = []
    pending = list(clients)
    for i, delay in enumerate((0, *waits)):
        if i:
            sleep(delay)
        started = now()
        cmd = [PY, FETCH, "--client", ",".join(pending), "--config", config]
        cmd += ["--no-snapshot"] if read_only else ["--out-dir", snapshots]
        code, output = runner(cmd, timeout=FETCH_TIMEOUT)
        res = parse_attempt(output, code, pending, started, snapshots, check_fresh=not read_only)
        for c in res:
            res[c]["at"] = started.isoformat(timespec="seconds")
        attempts.append({"n": i + 1, "at": started.isoformat(timespec="seconds"), "clients": list(pending), "exit": code,
                         "output": redact(output or "")[-6000:], "result": res})
        outcomes.update(res)
        pending = [c for c in pending if not res[c]["ok"] and res[c]["cause"] in RETRYABLE]
        if not pending:
            break
    failed = [c for c in clients if not outcomes[c]["ok"]]
    for c in failed:
        outcomes[c]["tries"] = sum(1 for a in attempts if c in a["clients"])
    return {"clients": list(clients), "outcomes": outcomes, "attempts": attempts, "failed": failed, "read_only": read_only}


# ------------------------------------------------------------------------------------------------ the words
def ps(path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def rerun_command(clients: list[str]) -> str:
    which = "all" if set(clients) >= set(ALL_CLIENTS) else ",".join(clients)
    return f"& {ps(PY)} {ps(THIS)} --clients {which} --once"


def check_command() -> str:
    """The read-only check, as a line to paste into PowerShell."""
    return f"& {ps(PY)} {ps(THIS)} --check-only"


def evidence_of(outcome: dict) -> str | None:
    m = re.search(r"kept at (.+?\.csv)", outcome.get("reason") or "")
    return m.group(1) if m else None


def cause_block(cause: str, failed: list[str], info: dict, outcomes: dict, snapshots: Path, context: str | None) -> tuple[str, list[str], str, str]:
    """(likely cause in one line, numbered steps, what you do, what the re-run does)."""
    key = info.get("key") or "(the key path in customer_sheets.json)"
    urls = [f"{LABELS.get(c, c)}: {info['clients'].get(c, {}).get('url') or '(the link is in customer_sheets.json)'}" for c in failed]
    rerun_does = "it fetches each failed sheet once, saves a fresh copy, and prints SHEET LOAD: HEALTHY, or the reason it still fails."
    if cause == "key":
        return ("The Google service-account key that reads the sheets is missing, unreadable, or no longer valid (deleted, disabled or expired in Google Cloud).",
                [f"Check the key file is there (prints True or False; it never shows the key):\n       Test-Path {ps(key)}",
                 "If it says False, or it says True and this alert keeps coming, make a new key: open https://console.cloud.google.com/iam-admin/serviceaccounts, "
                 "choose the project that holds the CFP sheet reader, click the service account, open the Keys tab, then Add key > Create new key > JSON. A file downloads.",
                 f"Put the downloaded file in place (change the name to the file that downloaded):\n       Move-Item \"$env:USERPROFILE\\Downloads\\<downloaded-file>.json\" {ps(key)} -Force",
                 "In the same Keys tab, delete the old key, so only the new one works."],
                "make the new key in Google Cloud and put the file in place. Only you can, because it needs your Google sign-in.", rerun_does)
    if cause == "config":
        return ("The settings file that names the sheets (customer_sheets.json) is missing, unreadable, or does not list a sheet.",
                [f"Check it is there (prints True or False):\n       Test-Path {ps(CONFIG)}",
                 "If it says False, restore it from your backup (right-click the CFP-Monitor folder > Restore previous versions). It holds the sheet ids and the key path, "
                 "so it is not in git on purpose.",
                 "If you cannot restore it, tell Claude 'customer_sheets.json is missing' and rebuild it together (it needs the four sheet links)."],
                "restore the file. Nothing in the repo can recreate it.", rerun_does)
    if cause == "sharing":
        return ("Google refused to let our reader open the sheet: its sharing with our service account was removed, or the sheet was moved or deleted.",
                [f"Show our reader's email address (prints only the address):\n       (Get-Content {ps(key)} -Raw | ConvertFrom-Json).client_email",
                 "Open each failed sheet:\n       " + "\n       ".join(urls),
                 "Click Share (top right). If that address is not listed, add it as Viewer and untick 'Notify people'. If you cannot share the sheet, ask whoever owns it to add the address as Viewer."],
                "share the sheet with our reader again. It needs a person signed in to Google.", rerun_does)
    if cause == "structure":
        kept = [e for e in (evidence_of(outcomes[c]) for c in failed) if e]
        need = sorted({col for c in failed for col in fcs.REQUIRED_BY_KIND.get(info["clients"].get(c, {}).get("kind", "awards" if c in AWARD_CLIENTS else "conference"), ())})
        return ("The sheet downloaded but its layout changed: a column we read is missing or renamed, the header row was edited, or the sheet came back empty.",
                [("Open the copy we kept of what Google sent:\n       " + "\n       ".join(f"notepad {ps(k)}" for k in kept)) if kept else "The error above says what is missing.",
                 "Open each failed sheet:\n       " + "\n       ".join(urls),
                 f"Row 1 must carry these column names, spelled exactly: {', '.join(need)} (an awards sheet also needs STATUS or SUBMISSION STATUS). "
                 "Put back any that were renamed or deleted, or ask whoever edits the sheet to.",
                 "If the change is on purpose (the sheet was redesigned), do not edit it: tell Claude 'the customer sheet layout changed' and give it the kept copy, and our reader is adapted."],
                "put the header row back (or ask for it), or hand the change to Claude.", rerun_does)
    if cause == "network":
        return ("This PC could not reach Google on any try over about 15 minutes: the internet was down, or Google was.",
                ["Check the internet works on this PC: open https://docs.google.com in a browser.",
                 "Check Google's status page: https://www.google.com/appsstatus/dashboard/",
                 "When both look fine, run the re-run below. Nothing in our setup needs changing."],
                "only confirm the internet and Google are up.", rerun_does)
    if cause == "software":
        return ("A program library our reader needs is missing on this PC (usually after an update).",
                ["Reinstall the project's libraries:\n       cd " + ps(ROOT) + "; uv sync"],
                "run the one command above.", rerun_does)
    if cause == "not_saved":
        return ("The sheet downloaded but no new copy was saved: the copy step refused it, or could not write to the folder.",
                ["Check there is free disk space:\n       Get-PSDrive C",
                 f"Check the copies folder exists (prints True or False):\n       Test-Path {ps(snapshots)}",
                 "Run the re-run below. If it fails the same way, tell Claude 'customer sheet copy not saved' and give it the evidence file named below."],
                "check disk space and the folder.", rerun_does)
    if cause == "never_ran":
        what, task, _cl = CONTEXTS.get(context or "", ("the weekend research", "CFP Weekly Re-Research (live markets)", ALL_CLIENTS))
        return (f"The research task did not start: {what} never ran today (the PC was off or asleep at 02:00, or the task is disabled).",
                [f"See what Task Scheduler says (LastRunTime, LastTaskResult, and State: Disabled means it was switched off):\n"
                 f"       Get-ScheduledTaskInfo -TaskName '{task}' | Format-List LastRunTime,LastTaskResult,NextRunTime; (Get-ScheduledTask -TaskName '{task}').State",
                 f"Start the research by hand. It runs exactly as the night run would: the sheets first, then the research, then the load and the recap "
                 f"(it costs the normal weekly research, nothing extra; it takes hours, leave the PC on):\n       Start-ScheduledTask -TaskName '{task}'",
                 f"Confirm it is running (State should say Running):\n       (Get-ScheduledTask -TaskName '{task}').State",
                 "If State said Disabled, it was switched off on purpose or by mistake: tell Claude before switching it back on."],
                "start the task (one command) and leave the PC on.",
                "you do not need it here: the started task loads the sheets itself. Use it only to see whether the sheets can be read at all.")
    if cause == "ran_no_copies":
        what, task, _cl = CONTEXTS.get(context or "", ("the weekend research", "CFP Weekly Re-Research (live markets)", ALL_CLIENTS))
        return (f"{what[0].upper() + what[1:]} ran today and finished, but did not save today's copies of these sheets (it stopped early, or skipped the sheet step).",
                [f"Open today's run log and search it for SHEET LOAD and STOPPED:\n       notepad (Get-ChildItem {ps(LOGS)} -Filter 'run_monthly_*.log' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName",
                 "Run the sheet load now (the re-run below).",
                 "If it loads, tell Claude 'the research ran on old customer sheets today' with the log: whether to run the research again is a decision (it costs a second research run)."],
                "read the log, run the re-run, and decide with Claude whether to research again.", rerun_does)
    reason = "; ".join(sorted({(outcomes[c].get("reason") or "")[:200] for c in failed}))
    return (f"An error our checker does not recognise: {reason}",
            ["Run the re-run below.", "If it fails again, tell Claude 'customer sheet load failed' and give it the evidence file named below."],
            "run the re-run; if it repeats, hand the evidence to Claude.", rerun_does)


def fmt_time(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M on %a %d %b %Y")
    except (TypeError, ValueError):
        return "an unknown time"


def last_good(failed: list[str], snapshots: Path, today: date) -> list[str]:
    out = []
    for c in failed:
        t = taken_at(newest_copy(c, snapshots))
        days = (today - t.date()).days if t else None
        out.append(f"{LABELS.get(c, c)}: " + (t.strftime("%a %d %b") + f" ({days} day{'' if days == 1 else 's'} old)" if t else "NONE on disk"))
    return out


def copies_from(failed: list[str], snapshots: Path) -> str:
    """The date of the OLDEST last good copy among the failed sheets, for the follow-up subject."""
    ts = [taken_at(newest_copy(c, snapshots)) for c in failed]
    if not ts or any(t is None for t in ts):
        return "before this week (a sheet has no copy at all)" if ts else "the last good copy"
    return min(ts).strftime("%a %d %b %Y")


def cause_sections(result: dict, info: dict, snapshots: Path, context: str | None) -> list[str]:
    out, failed = result["outcomes"], result["failed"]
    causes: list[str] = []
    for c in failed:
        if out[c]["cause"] not in causes:
            causes.append(out[c]["cause"])
    L: list[str] = []
    for n, cause in enumerate(causes, 1):
        group = [c for c in failed if out[c]["cause"] == cause]
        line, steps, you, rerun = cause_block(cause, group, info, out, snapshots, context)
        head = "LIKELY CAUSE" + (f" {n} of {len(causes)} ({', '.join(LABELS.get(c, c) for c in group)})" if len(causes) > 1 else "")
        L += [f"{head}: {line}", "", "HOW TO FIX IT"]
        k = 0
        for k, st in enumerate(steps, 1):
            L.append(f"{k}. {st}")
        L.append(f"{k + 1}. Re-run just the sheet load and confirm it worked (paste into PowerShell):")
        L.append(f"       {rerun_command(group)}")
        L.append("   It ends with one line: SHEET LOAD: HEALTHY (fixed) or SHEET LOAD: FAILED with the reason.")
        L.append(f"   What you do yourself: {you}")
        L.append(f"   What the re-run does for you: {rerun}")
        L.append("")
    return L


def compose(result: dict, context: str | None, info: dict, snapshots: Path, hold: tuple | None = None, evidence: Path | None = None,
            today: date | None = None, test: bool = False, meaning: list[str] | None = None, mode: str | None = None) -> tuple[str, str]:
    """(subject, plain-text body) for Matt. `hold` = (hours, why shorter, deadline) for a guarded load; `meaning` replaces the WHAT THIS
    MEANS lines (the 03:00 check); `mode` is 'hold' (default: the research does NOT start while the sheets fail) or 'proceed' (old copies).
    No secret: paths and names only, and redact() runs over the whole text."""
    today = today or date.today()
    mode = mode or on_fail_mode()
    out = result["outcomes"]
    failed = result["failed"]
    fine = [c for c in result["clients"] if c not in failed]
    what, task, _cl = CONTEXTS.get(context or "", (None, None, None))
    What = what[0].upper() + what[1:] if what else None
    L = [SUBJECT, ""]
    if test:
        L += ["THIS IS A TEST. Nothing failed: this is what the real alert looks like, sent once to prove it reaches you.", ""]
    L.append("WHAT FAILED")
    for c in failed:
        o = out[c]
        tries = o.get("tries", 1)
        L.append(f"- {LABELS.get(c, c)} ({c}): failed at {fmt_time(o.get('at'))}" + (f", after {tries} tries over about 15 minutes" if tries > 1 else "")
                 + f". Error: {(o.get('reason') or '')[:300]}")
    if fine:
        L.append("Loaded fine: " + ", ".join(LABELS.get(c, c) for c in fine) + ".")
    L += ["", "WHAT THIS MEANS"]
    if meaning is not None:
        L += meaning
    elif What and hold is not None and hold[0] > 0:
        hours, why, deadline = hold
        L.append(f"{What} is WAITING for the sheets and has NOT started. It tries again every {HOLD_POLL_S // 60} minutes until {deadline:%H:%M} "
                 f"({fmt_h(hours)} after the first failure).")
        L.append(f"- If they load by then, the research starts by itself on fresh copies and you get a second email: '{SUBJECT_LOADED}'.")
        if mode == "hold":
            L.append(f"- If not, at {deadline:%H:%M} the research is HELD: it does NOT start, nothing is researched, nothing is spent (your rule, 2026-11-13). "
                     f"You get: '{SUBJECT_HELD}', with the commands to start it once the sheets load.")
        else:
            L.append(f"- If not, at {deadline:%H:%M} the research goes ahead on the last good copies and you get: '{SUBJECT_STILL.format(copies='<date>')}'.")
        L.append(f"Fix it while it waits: the waiting run notices your fix within {HOLD_POLL_S // 60} minutes by itself (the re-run below only shows you sooner).")
        if why:
            L.append(f"The wait is shorter than {HOLD_DEFAULT_H:g} hours: {why}.")
    elif What and mode == "hold":
        L.append(f"{What} is HELD: it did NOT start, because the sheets did not load. Nothing is researched and nothing is spent (your rule, 2026-11-13).")
        if hold is not None and hold[1]:
            L.append(f"It does not wait for the sheets: {hold[1]}.")
    elif What:
        L.append(f"{What} goes ahead with the last good copy of each failed sheet, so anything the customer changed since then is not seen this week.")
        if hold is not None and hold[1]:
            L.append(f"It does not wait for the sheets: {hold[1]}.")
    else:
        L.append("Anything that reads these sheets uses the last good copy until this is fixed.")
    L.append("Last good copy: " + "; ".join(last_good(failed, snapshots, today)) + ".")
    L.append("")
    L += cause_sections(result, info, snapshots, context)
    if What and mode == "hold" and meaning is None:
        L += held_steps(context)
    L.append("EVIDENCE")
    L.append(f"- Every try and its output: {evidence}" if evidence else "- (no evidence file was written)")
    L.append(f"- This text is also on your Desktop: {fcs.alert_paths()[-1]}")
    L.append("")
    L.append("This email goes to you only. No secret is in it: the key file is named by its path, never its contents.")
    subject = ("[TEST] " if test else "") + SUBJECT
    return subject, redact("\n".join(L) + "\n")


def compose_followup(loaded: bool, result: dict, context: str | None, info: dict, snapshots: Path, first: datetime, at: datetime,
                     evidence: Path | None, failed_at_first: list[str], mode: str | None = None) -> tuple[str, str]:
    """The second email after a wait: loaded (the research starts on fresh copies) or still not loaded: HELD (default, it does not start) or,
    with CFP_SHEETS_ON_FAIL=proceed, it goes ahead on old copies."""
    mode = mode or on_fail_mode()
    what = CONTEXTS.get(context or "", ("the research", None, None))[0]
    What = what[0].upper() + what[1:]
    waited = max(0, int(round((at - first).total_seconds() / 60)))
    names = ", ".join(LABELS.get(c, c) for c in failed_at_first)
    if loaded:
        subject = SUBJECT_LOADED
        L = [subject, "",
             f"The customer sheets that failed at {first:%H:%M} loaded at {at:%H:%M}, after waiting {waited} minutes: {names}.",
             f"{What} has started on fresh copies. Nothing for you to do.",
             "If you fixed something, that worked. If you did nothing, the fault cleared by itself.", "",
             f"Evidence: {evidence}" if evidence else "Evidence: (no evidence file was written)"]
        return subject, redact("\n".join(L) + "\n")
    copies = copies_from(result["failed"], snapshots)
    subject = SUBJECT_HELD if mode == "hold" else SUBJECT_STILL.format(copies=copies)
    L = [subject, "", "STILL NOT LOADED"]
    for c in result["failed"]:
        o = result["outcomes"][c]
        L.append(f"- {LABELS.get(c, c)} ({c}): still failing at {at:%H:%M} after waiting {waited} minutes since {first:%H:%M}. Error: {(o.get('reason') or '')[:300]}")
    back = [c for c in failed_at_first if c not in result["failed"]]
    if back:
        L.append("Loaded during the wait: " + ", ".join(LABELS.get(c, c) for c in back) + ".")
    if mode == "hold":
        L += ["", "WHAT THIS MEANS",
              f"{What} is HELD: it did NOT start, because the sheets did not load. Nothing is researched and nothing is spent (your rule, 2026-11-13).",
              "Last good copy: " + "; ".join(last_good(result["failed"], snapshots, at.date())) + ".",
              "The recap and the Sunday check show this weekend as HELD until the research has run.", ""]
        L += cause_sections(result, info, snapshots, context)
        L += held_steps(context)
    else:
        L += ["", "WHAT THIS MEANS",
              f"{What} is going ahead now on the last good copies, so anything the customer changed since then is not seen this week.",
              "Last good copy: " + "; ".join(last_good(result["failed"], snapshots, at.date())) + ".",
              "The recap and the Sunday check show this weekend as DEGRADED.", ""]
        L += cause_sections(result, info, snapshots, context)
    L += ["EVIDENCE", f"- Every try and its output: {evidence}" if evidence else "- (no evidence file was written)",
          f"- This text is also on your Desktop: {fcs.alert_paths()[-1]}", "",
          "This email goes to you only. No secret is in it: the key file is named by its path, never its contents."]
    return subject, redact("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------ evidence, file, email
def write_evidence(payload: dict, now: datetime, qa_root: Path | None = None) -> Path | None:
    try:
        d = Path(qa_root or QA_ROOT) / now.strftime("%Y-%m-%d")
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"sheet_load_{now.strftime('%H%M%S')}.json"
        p.write_text(redact(json.dumps(payload, indent=2, default=str)), encoding="utf-8")
        return p
    except Exception:                                                         # noqa: BLE001
        return None


def write_alert_file(body: str, paths=None) -> list[str]:
    written = []
    for target in (paths if paths is not None else fcs.alert_paths()):
        try:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_text(body, encoding="utf-8")
            written.append(str(target))
        except Exception:                                                     # noqa: BLE001
            pass
    return written


def already_sent(today: date, state: Path | None = None) -> str | None:
    try:
        s = json.loads(Path(state or SENT_STATE).read_text(encoding="utf-8"))
        return s.get("sent_at") if s.get("date") == today.isoformat() else None
    except Exception:                                                         # noqa: BLE001
        return None


def send(subject: str, body: str, today: date, now: datetime, mailer=None, state: Path | None = None, test: bool = False,
         once_a_day: bool = True) -> str:
    """'sent', 'already sent at ...', 'not sent: ...'. At most one CRITICAL alert a day; a test send and a follow-up are never counted."""
    if not test and once_a_day:
        prior = already_sent(today, state)
        if prior:
            return f"already sent at {prior[11:16]} today (one alert a day)"
    if mailer is None:
        from src.cfp_monitor.alerts import maybe_send_email as mailer       # noqa: PLC0415
    try:
        ok = mailer(subject, redact(body), to_env="CFP_RECAP_TO")
    except Exception as exc:                                                  # noqa: BLE001
        return f"not sent: {type(exc).__name__} from the mailer"
    if not ok:
        return "not sent: the mail settings (CFP_RECAP_TO, CFP_SMTP_*) are not all set"
    if not test and once_a_day:
        try:
            state = Path(state or SENT_STATE)
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"date": today.isoformat(), "sent_at": now.isoformat(timespec="seconds"), "subject": subject}), encoding="utf-8")
        except Exception:                                                     # noqa: BLE001
            pass
    return "sent"


def alert(result: dict, context: str | None, config: Path, snapshots: Path, now: datetime, env: dict | None = None, mailer=None,
          qa_root: Path | None = None, state: Path | None = None, email: bool = True, alert_files=None, hold: tuple | None = None,
          meaning: list[str] | None = None, mode: str | None = None) -> dict:
    """Evidence, the Desktop file and (once a day) the email. Returns {'evidence', 'files', 'email', 'subject', 'body'}."""
    info = config_info(config)
    evidence = write_evidence({"context": context, "at": now.isoformat(timespec="seconds"),
                               "wait_hours": hold[0] if hold else None, **result}, now, qa_root)
    subject, body = compose(result, context, info, snapshots, hold, evidence, now.date(), meaning=meaning, mode=mode)
    files = write_alert_file(body, alert_files)
    status = send(subject, body, now.date(), now, mailer, state) if email else "not sent: --once (you are at the keyboard)"
    return {"evidence": evidence, "files": files, "email": status, "subject": subject, "body": body}


def write_status(context: str | None, verdict: str, result: dict, snapshots: Path, at: datetime, waited_min: int = 0,
                 path: Path | None = None, note: str = "") -> None:
    """runs_out/sheet_load_status.json: the last load of each research (friday / saturday), for the recap and the Sunday gate. Never raises."""
    if context not in CONTEXTS:
        return
    try:
        p = Path(path or STATUS)
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        copies = {}
        for c in result["clients"]:
            t = taken_at(newest_copy(c, snapshots))
            copies[c] = t.isoformat() if t else None
        d[context] = {"date": at.date().isoformat(), "at": at.isoformat(timespec="seconds"), "verdict": verdict,
                      "failed": list(result["failed"]), "copies": copies, "waited_min": waited_min, "note": note}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:                                                         # noqa: BLE001
        pass


def read_status(path: Path | None = None) -> dict:
    try:
        return json.loads(Path(path or STATUS).read_text(encoding="utf-8"))
    except Exception:                                                         # noqa: BLE001
        return {}


def verdict_line(result: dict, extra: str = "") -> str:
    n, f = len(result["clients"]), result["failed"]
    if not f:
        return f"SHEET LOAD: HEALTHY - {n} of {n} sheet(s) loaded" + (" (read only, nothing saved)" if result.get("read_only") else "") + extra
    causes = sorted({result["outcomes"][c]["cause"] for c in f})
    return f"SHEET LOAD: FAILED - {len(f)} of {n} sheet(s) did not load ({', '.join(f)}; cause: {', '.join(causes)})" + extra


def held_line(result: dict, context: str | None, waited: int, snapshots: Path) -> str:
    """The verdict when the research does NOT start (exit 6). The recap reads the LAST 'SHEET LOAD:' line of the log, so this must stay one line."""
    f, n = result["failed"], len(result["clients"])
    causes = sorted({result["outcomes"][c]["cause"] for c in f})
    what = CONTEXTS.get(context or "", ("the research", None, None))[0]
    return (f"SHEET LOAD: HELD - {len(f)} of {n} sheet(s) still not loaded ({', '.join(f)}; cause: {', '.join(causes)})"
            + (f" after waiting {waited} min" if waited else "")
            + f"; {what} did NOT start: nothing researched, nothing spent. After the fix, start it: {start_research_command(context)}")


# ------------------------------------------------------------------------------------------------ the customer-context hold (ACT-76)
def compose_context_held(context: str | None, detail: str, today: date | None = None) -> tuple[str, str]:
    """(subject, body): the customer context (step 0a4) did not build, so the research is HELD. Sent by run_monthly.ps1 through --held-notice context.
    Plain words, exact commands, no secret (redact() over the whole text)."""
    what = CONTEXTS.get(context or "", ("the research", None, None))[0]
    What = what[0].upper() + what[1:]
    mk = research_markets(context)
    detail = " ".join((detail or "(no detail was passed)").split())[:400]
    L = [SUBJECT_CONTEXT_HELD, "", "WHAT FAILED",
         "- Step 0a4 (the customer's own sheet row, put in front of the research as context) did not build. " + f"What it said: {detail}", "",
         "WHAT THIS MEANS",
         f"{What} is HELD: it did NOT start. Nothing is researched and nothing is spent. The customer sheets themselves loaded; the context made from them did not.",
         "Your rule is that the customer data must be loaded and turned into context before the research runs, so this holds it the same way a failed sheet load does.", "",
         "WHAT TO DO",
         "1. See what the context step says now. This changes nothing (report only):",
         f"       & {ps(PY)} {ps(HERE / 'customer_row_context.py')} --markets {mk}",
         "   It prints one line that starts CUSTOMER CONTEXT: HEALTHY, DEGRADED or FAILED. HEALTHY (or DEGRADED with rows carrying the customer's row) is good.",
         "2. If it still FAILS, the line says why. Send it to the Claude session that built it, or read runs_out\\qa\\<date>\\customer_context.csv.",
         "3. When it is good, start the research (the normal full job, from its own start):",
         f"       {start_research_command(context)}",
         "4. Only if you decide to research WITHOUT the customer context (your choice, by hand): in PowerShell, run",
         f"       $env:CFP_CONTEXT_ON_FAIL = 'proceed'; & {ps(MARKETS / 'run_monthly.ps1')} -Markets {mk}",
         "   The research then runs as it did before this step existed, and the recap says the context was missing.", "",
         "This email goes to you only. No secret is in it."]
    return SUBJECT_CONTEXT_HELD, redact("\n".join(L) + "\n")


# ------------------------------------------------------------------------------------------------ the guarded load (Friday, Saturday, the person's re-run)
def clear_alert_files(alert_files=None) -> None:
    """The sheets loaded: the Desktop alert is out of date. Never raises."""
    try:
        if alert_files is None:
            fcs.clear_alert()
        else:
            for f in alert_files:
                Path(f).unlink(missing_ok=True)
    except Exception:                                                         # noqa: BLE001
        pass


def safe_load(clients, config, snapshots, waits, sleep, runner, now) -> dict:
    try:
        return load(clients, config, snapshots, waits=waits, sleep=sleep, runner=runner, now=now)
    except Exception as exc:                                                  # noqa: BLE001
        return {"clients": list(clients), "failed": list(clients), "attempts": [], "read_only": False,
                "outcomes": {c: {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "cause": "unknown",
                                 "at": now().isoformat(timespec="seconds")} for c in clients}}


def guarded_load(clients: list[str], context: str | None, config: Path | None = None, snapshots: Path | None = None, once: bool = False,
                 env: dict | None = None, mailer=None, sleep=time.sleep, runner=None, now=datetime.now, qa_root: Path | None = None,
                 state: Path | None = None, alert_files=None, task_reader=None, say=None, status_path: Path | None = None
                 ) -> tuple[int, dict, list[str]]:
    """(exit code, result, printed lines; the LAST line is the verdict). Never raises.

    Fail -> CRITICAL email -> wait up to CFP_SHEETS_HOLD_HOURS (default 2, Matt 2026-11-10: "Wait up to 2 hours"), one try every 10 minutes ->
    loaded: second email, exit 0, the research starts on fresh copies | still failing: second email, exit 6 HELD, the research does NOT start
    (Matt 2026-11-13, D66 = B). With CFP_SHEETS_ON_FAIL=proceed (by hand only) it is the 11-10 rule instead: exit 1, DEGRADED, research on old copies."""
    mode = on_fail_mode(env)
    config, snapshots = Path(config or CONFIG), Path(snapshots or SNAPSHOTS)
    say = say or (lambda line: print(line, flush=True))
    first = now()
    result = safe_load(clients, config, snapshots, () if once else WAITS, sleep, runner, now)
    lines: list[str] = []
    if not result["failed"]:
        clear_alert_files(alert_files)
        tries = len(result["attempts"])
        lines.append(verdict_line(result, f" at {now().strftime('%H:%M')}" + (f", on try {tries}" if tries > 1 else "")))
        if not once:
            write_status(context, "HEALTHY", result, snapshots, now(), path=status_path)
        return 0, result, lines
    if once:
        a = alert(result, context, config, snapshots, now(), env, mailer, qa_root, state, email=False, alert_files=alert_files)
        lines += [*a["body"].splitlines(), ""]                         # the fix first: the verdict stays the LAST line (Codex review, 2026-11-10)
        lines.append(verdict_line(result, f"; email {a['email']}; evidence: {a['evidence']}"))
        return 1, result, lines

    hours, why = hold_plan(context, env, task_reader)
    deadline = first + timedelta(hours=hours)
    a = alert(result, context, config, snapshots, now(), env, mailer, qa_root, state, alert_files=alert_files, hold=(hours, why, deadline), mode=mode)
    wait_txt = (f"; waiting up to {fmt_h(hours)} (until {deadline:%H:%M}) for the sheets" if hours > 0 else "; no wait (" + (why or "0 hours") + ")")
    lines.append(verdict_line(result, f"; email {a['email']}; evidence: {a['evidence']}{wait_txt}"))
    say(lines[-1])
    if hours <= 0:
        if mode == "hold":
            write_status(context, "HELD", result, snapshots, now(), path=status_path, note=why)
            lines.append(held_line(result, context, 0, snapshots))
            return HELD_EXIT, result, lines
        lines.append(verdict_line(result, "; the research goes ahead on the last good copies"))
        write_status(context, "FAILED", result, snapshots, now(), path=status_path, note=why)
        return 1, result, lines

    failed_at_first = list(result["failed"])
    n = len(result["attempts"])
    max_tries = int(hours * 3600 // HOLD_POLL_S) + 2              # a stuck clock (or a fake sleep) can never make this loop forever
    tries = 0
    while result["failed"] and now() < deadline and tries < max_tries:
        tries += 1
        sleep(max(1.0, min(HOLD_POLL_S, (deadline - now()).total_seconds())))
        again = safe_load(list(result["failed"]), config, snapshots, (), sleep, runner, now)
        for att in again["attempts"]:
            n += 1
            result["attempts"].append({**att, "n": n, "during_wait": True})
        for c, o in again["outcomes"].items():
            o["tries"] = result["outcomes"][c].get("tries", 1) + 1
            result["outcomes"][c] = o
        result["failed"] = [c for c in result["clients"] if not result["outcomes"][c]["ok"]]
        line = (f"SHEET WAIT: try at {now():%H:%M} - " + ("all loaded" if not result["failed"] else
                f"{len(result['failed'])} still failing ({', '.join(result['failed'])}); next try in {HOLD_POLL_S // 60} min, until {deadline:%H:%M}"))
        lines.append(line)
        say(line)
    at = now()
    waited = max(0, int(round((at - first).total_seconds() / 60)))
    info = config_info(config)
    evidence = write_evidence({"context": context, "at": at.isoformat(timespec="seconds"), "wait_hours": hours, "waited_min": waited, **result},
                              at, qa_root)
    subject, body = compose_followup(not result["failed"], result, context, info, snapshots, first, at, evidence, failed_at_first, mode=mode)
    st = send(subject, body, at.date(), at, mailer, state, once_a_day=False)
    if not result["failed"]:
        clear_alert_files(alert_files)
        write_status(context, "RECOVERED", result, snapshots, at, waited, path=status_path)
        lines.append(f"SHEET LOAD: HEALTHY - all {len(result['clients'])} sheet(s) loaded at {at:%H:%M} after waiting {waited} min; "
                     f"email '{subject}' {st}; evidence: {evidence}")
        return 0, result, lines
    write_alert_file(body, alert_files)
    if mode == "hold":
        write_status(context, "HELD", result, snapshots, at, waited, path=status_path, note=why)
        lines.append(held_line(result, context, waited, snapshots) + f"; email {st}; evidence: {evidence}")
        return HELD_EXIT, result, lines
    write_status(context, "DEGRADED", result, snapshots, at, waited, path=status_path, note=why)
    causes = sorted({result["outcomes"][c]["cause"] for c in result["failed"]})
    lines.append(f"SHEET LOAD: DEGRADED - {len(result['failed'])} of {len(result['clients'])} sheet(s) still not loaded after waiting {waited} min "
                 f"({', '.join(result['failed'])}; cause: {', '.join(causes)}); the research runs on copies from {copies_from(result['failed'], snapshots)}; "
                 f"email {st}; evidence: {evidence}")
    return 1, result, lines


# ------------------------------------------------------------------------------------------------ the dead-man check (03:00 Friday and Saturday)
def todays_run_logs(today: date, logs: Path | None = None) -> list[Path]:
    logs = Path(logs or LOGS)
    return sorted(Path(logs).glob(f"run_monthly_{today.strftime('%Y%m%d')}-*.log")) if Path(logs).is_dir() else []


def failures_in_log(log: Path) -> list[str]:
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except Exception:                                                         # noqa: BLE001
        return []
    return [ln.strip() for ln in text.splitlines() if ": FAILED - " in ln]


def deadman(kind: str, snapshots: Path | None = None, logs: Path | None = None, config: Path | None = None, now=datetime.now, sleep=time.sleep,
            env: dict | None = None, mailer=None, qa_root: Path | None = None, state: Path | None = None, task_reader=None,
            start_grace_s: int = DEADMAN_START_GRACE_S, poll_s: int = DEADMAN_POLL_S, alert_files=None) -> tuple[int, list[str]]:
    """Fetches nothing. Are today's copies there for the sheets this day's research takes? If not, which of three cases (Matt, 2026-11-10):
      did_not_start  no run log today and the task's last run is not today -> CRITICAL email: how to start it by hand
      running        the task is running (or its log changed in the last 15 minutes) -> NO email: the run alerts and waits by itself
      ran_no_copies  the task ran today, is not running, and today's copies are missing -> CRITICAL email, cause read from today's run log"""
    snapshots, logs, config = Path(snapshots or SNAPSHOTS), Path(logs or LOGS), Path(config or CONFIG)
    what, task, clients = CONTEXTS[kind]
    reader = task_reader or task_info
    today = now().date()

    def stale() -> list[str]:
        out = []
        for c in clients:
            t = taken_at(newest_copy(c, snapshots))
            if not (t and t.date() == today):
                out.append(c)
        return out

    def look() -> tuple[str, dict]:
        try:
            info = reader(task) or {}
        except Exception:                                                     # noqa: BLE001
            info = {}
        cut_ts = now().timestamp() - 15 * 60
        fresh_log = any(p.stat().st_mtime >= cut_ts for p in todays_run_logs(today, logs))
        if info.get("state") == "Running" or fresh_log:
            return "running", info
        last = info.get("last_run")
        if todays_run_logs(today, logs) or (last and last.date() == today):
            return "ran_no_copies", info
        return "did_not_start", info

    missing = stale()
    if not missing:
        return 0, [f"SHEET DEADMAN: HEALTHY - today's copies of all {len(clients)} sheet(s) for {kind} are there"]
    case, info = look()
    waited = 0
    # The PC woke for this check: a task that missed 02:00 starts by itself within a minute or two (StartWhenAvailable).
    while case == "did_not_start" and waited < start_grace_s:
        sleep(poll_s)
        waited += poll_s
        missing = stale()
        if not missing:
            return 0, [f"SHEET DEADMAN: HEALTHY - today's copies of all {len(clients)} sheet(s) for {kind} are there"]
        case, info = look()
    if case == "running":
        return 0, [f"SHEET DEADMAN: RUNNING - {len(missing)} of {len(clients)} sheet(s) have no copy from today yet ({', '.join(missing)}), but "
                   f"'{task}' is running: it raises its own alert and waits for the sheets. Nothing sent."]
    logs_today = todays_run_logs(today, logs)
    last = info.get("last_run")
    last_txt = f"its last run was {last:%a %d %b %H:%M}" if last else "Task Scheduler could not be read"
    outcomes = {}
    for c in clients:
        if c not in missing:
            outcomes[c] = {"ok": True, "reason": "", "cause": None}
            continue
        cp = newest_copy(c, snapshots)
        if case == "did_not_start":
            cause, reason = "never_ran", f"'{task}' did not start today ({last_txt}; no run log for today in {logs})"
        else:
            fl = next((ln for f in logs_today for ln in failures_in_log(f) if ln.startswith(f"{c}: FAILED - ")), None)
            if fl:
                reason = fl.split(": FAILED - ", 1)[1]
                cause = classify(reason)
            else:
                cause = "ran_no_copies"
                reason = (f"'{task}' ran today ({last_txt}) and is no longer running, but took no copy of this sheet"
                          + (f"; run log: {logs_today[-1]}" if logs_today else ""))
        outcomes[c] = {"ok": False, "reason": reason + f"; newest copy: {cp.name if cp else 'none'}", "cause": cause,
                       "at": now().isoformat(timespec="seconds"), "tries": 1}
    result = {"clients": list(clients), "outcomes": outcomes, "failed": missing, "attempts": [], "read_only": True,
              "run_logs_today": [str(p) for p in logs_today], "case": case, "task": {k: str(v) for k, v in info.items()}}
    What = what[0].upper() + what[1:]
    if case == "did_not_start":
        meaning = [f"{What} did NOT start today, so nothing has been researched yet and no sheet was read.",
                   "Starting it by hand (step below) runs it exactly as the night run would: it takes the sheets first, then researches."]
    else:
        meaning = [f"{What} ran today but did not take today's copies of these sheets, so it researched with the last good copies.",
                   "Anything the customer changed since then is not seen this week, unless the sheet load and the research are run again."]
    a = alert(result, kind, config, snapshots, now(), env, mailer, qa_root, state, alert_files=alert_files, meaning=meaning)
    label = {"did_not_start": "the research task did not start", "ran_no_copies": "the research ran but today's copies are missing"}[case]
    return 1, [f"SHEET DEADMAN: FAILED - {label}: {len(missing)} of {len(clients)} sheet(s) have no copy from today ({', '.join(missing)}); "
               f"email {a['email']}; evidence: {a['evidence']}"]


# ------------------------------------------------------------------------------------------------ the read-only check (Thursday)
def read_check(config: Path = CONFIG, runner=None, now=datetime.now) -> dict:
    """Can every sheet be read right now? Downloads and checks the shape; saves no copy, loads nothing, sends nothing. One try."""
    return load(expand("all", config), config, SNAPSHOTS, waits=(), runner=runner, now=now, read_only=True)


def fix_summary(result: dict, config: Path = CONFIG) -> list[str]:
    """One line per failed sheet with its likely cause, for the Thursday pre-flight."""
    info = config_info(config)
    out = []
    for c in result["failed"]:
        o = result["outcomes"][c]
        line, _steps, you, _r = cause_block(o["cause"], [c], info, result["outcomes"], SNAPSHOTS, None)
        out.append(f"{LABELS.get(c, c)} cannot be read: {line} You: {you} Error: {(o.get('reason') or '')[:200]}")
    return out


def sample_result(now: datetime) -> dict:
    return {"clients": list(ALL_CLIENTS), "failed": ["utility"], "attempts": [], "read_only": False,
            "outcomes": {"arnica": {"ok": True}, "arnica-awards": {"ok": True}, "utility-awards": {"ok": True},
                         "utility": {"ok": False, "cause": "sharing", "tries": 3, "at": now.isoformat(timespec="seconds"),
                                     "reason": "403 from the export endpoint. The service account exists but is not allowed to read this sheet. (SAMPLE: nothing failed)"}}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clients", default="all", help="'all' or a comma list of client keys from customer_sheets.json")
    ap.add_argument("--context", choices=sorted(CONTEXTS), help="which research this load feeds (the wording of the email)")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--snapshots", default=str(SNAPSHOTS))
    ap.add_argument("--once", action="store_true", help="one try, no email, no wait: the person's re-run")
    ap.add_argument("--deadman", choices=[*sorted(CONTEXTS), "auto"], help="fetch nothing; are today's copies there? auto = by weekday (the 03:00 task)")
    ap.add_argument("--check-only", action="store_true", help="read-only: can every sheet be read now? (saves nothing, sends nothing)")
    ap.add_argument("--test-send", action="store_true", help="send ONE '[TEST] ...' email with a sample body")
    ap.add_argument("--held-notice", choices=["context"], help="send the CRITICAL 'research HELD' email for a failed step (run_monthly.ps1, ACT-76)")
    ap.add_argument("--detail", default="", help="with --held-notice: what the failed step said (one line)")
    a = ap.parse_args(argv)
    config, snapshots = Path(a.config), Path(a.snapshots)
    try:
        if a.held_notice:
            now = datetime.now()
            subj, body = compose_context_held(a.context, a.detail, now.date())
            files = write_alert_file(body)
            st = send(subj, body, now.date(), now, once_a_day=False)
            print(f"RESEARCH HELD NOTICE: email {st}; the same text is on the Desktop ({len(files)} file(s))")
            return 0 if st == "sent" else 2
        if a.test_send:
            now = datetime.now()
            hours, why = hold_plan("saturday")
            subj, body = compose(sample_result(now), "saturday", config_info(config), snapshots, (hours, why, now + timedelta(hours=hours)), None,
                                 now.date(), test=True)
            st = send(subj, body, now.date(), now, test=True)
            print(f"SHEET LOAD TEST: {st} at {now.strftime('%Y-%m-%d %H:%M:%S')} - subject '{subj}'")
            return 0 if st == "sent" else 2
        if a.deadman:
            kind = a.deadman if a.deadman != "auto" else {4: "friday", 5: "saturday"}.get(datetime.now().weekday())
            if kind is None:
                print("SHEET DEADMAN: HEALTHY - nothing to check today (it checks Friday and Saturday only)")
                return 0
            code, lines = deadman(kind, snapshots, config=config)
            print("\n".join(lines))
            return code
        if a.check_only:
            r = read_check(config)
            for ln in fix_summary(r, config):
                print("  - " + ln)
            print(verdict_line(r))                                         # the verdict is the LAST line (Codex review, 2026-11-10)
            return 0 if not r["failed"] else 1
        code, _r, lines = guarded_load(expand(a.clients, config), a.context, config, snapshots, once=a.once)
        print("\n".join(lines))
        return code
    except Exception as exc:                                                  # noqa: BLE001
        print(f"SHEET LOAD: DEGRADED - the check itself failed ({type(exc).__name__}: {exc})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
