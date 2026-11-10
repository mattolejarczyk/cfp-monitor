"""The customer sheets must load before the research. Retry, then ONE plain email that says what broke and how to fix it.

    python scripts/customer_sheet_load.py --clients all --context saturday       # fetch + copy, 3 tries over 15 min, CRITICAL email if still failing
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

IT NEVER STOPS THE RESEARCH ON ITS OWN. HOLD = one switch: with the environment variable CFP_SHEETS_HOLD_RESEARCH=1 a failed load exits 6
and run_monthly.ps1 (patch ACT-73) ends the run before the research; without it the research goes ahead on the last good copy and the email
says so. Exit codes: 0 HEALTHY, 1 FAILED, 2 DEGRADED (could not check), 6 HELD (FAILED and the hold switch is on).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
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
MARKETS = Path(os.environ.get("CFP_MARKETS_DIR") or Path.home() / "Desktop" / "Nicolia-PR-Prime" / "Markets")
SNAPSHOTS = MARKETS / "customer_snapshots"
LOGS = MARKETS / "logs"

SUBJECT = "CFP customer sheets failed to load - CRITICAL ERROR"
HOLD_VAR = "CFP_SHEETS_HOLD_RESEARCH"
HELD_EXIT = 6
WAITS = (300, 600)                       # tries at 0, +5 and +15 minutes
FETCH_TIMEOUT = 600
DEADMAN_GRACE_S = 25 * 60                # a research run that started late (the PC woke at 03:00) gets this long to take its copies
DEADMAN_POLL_S = 120

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
        return (f"{what[0].upper() + what[1:]} did not take today's copies: the PC was off or asleep at 02:00, the task did not start, or it stopped before the sheets.",
                [f"See whether the task started (look at LastRunTime and LastTaskResult):\n       Get-ScheduledTaskInfo -TaskName '{task}' | Format-List LastRunTime,LastTaskResult,NextRunTime",
                 "Run the sheet load now (the re-run below).",
                 f"If the research has not run today, start it (it takes the sheets again first; it costs the normal weekly research, nothing extra):\n       Start-ScheduledTask -TaskName '{task}'"],
                "find out why the job did not run, then start it.", rerun_does)
    reason = "; ".join(sorted({(outcomes[c].get("reason") or "")[:200] for c in failed}))
    return (f"An error our checker does not recognise: {reason}",
            ["Run the re-run below.", "If it fails again, tell Claude 'customer sheet load failed' and give it the evidence file named below."],
            "run the re-run; if it repeats, hand the evidence to Claude.", rerun_does)


def fmt_time(iso: str | None) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M on %a %d %b %Y")
    except (TypeError, ValueError):
        return "an unknown time"


def compose(result: dict, context: str | None, info: dict, snapshots: Path, hold: bool, evidence: Path | None = None,
            today: date | None = None, test: bool = False) -> tuple[str, str]:
    """(subject, plain-text body) for Matt. No secret: paths and names only, and redact() runs over the whole text."""
    today = today or date.today()
    out = result["outcomes"]
    failed = result["failed"]
    fine = [c for c in result["clients"] if c not in failed]
    what, task, _cl = CONTEXTS.get(context or "", (None, None, None))
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
    lastgood = []
    for c in failed:
        t = taken_at(newest_copy(c, snapshots))
        days = (today - t.date()).days if t else None
        lastgood.append(f"{LABELS.get(c, c)}: " + (t.strftime("%a %d %b") + f" ({days} day{'' if days == 1 else 's'} old)" if t else "NONE on disk"))
    if hold and what:
        L.append(f"The hold switch is ON ({HOLD_VAR}=1): {what} has NOT started and waits for you. After the fix, start it again:")
        L.append(f"       Start-ScheduledTask -TaskName '{task}'")
    elif what:
        L.append(f"{what[0].upper() + what[1:]} goes ahead with the last good copy of each failed sheet, so anything the customer changed since then is not seen this week.")
    else:
        L.append("Anything that reads these sheets uses the last good copy until this is fixed.")
    L.append("Last good copy: " + "; ".join(lastgood) + ".")
    L.append("")
    causes = []
    for c in failed:
        if out[c]["cause"] not in causes:
            causes.append(out[c]["cause"])
    for n, cause in enumerate(causes, 1):
        group = [c for c in failed if out[c]["cause"] == cause]
        line, steps, you, rerun = cause_block(cause, group, info, out, snapshots, context)
        head = "LIKELY CAUSE" + (f" {n} of {len(causes)} ({', '.join(LABELS.get(c, c) for c in group)})" if len(causes) > 1 else "")
        L += [f"{head}: {line}", "", "HOW TO FIX IT"]
        k = 0
        for k, s in enumerate(steps, 1):
            L.append(f"{k}. {s}")
        L.append(f"{k + 1}. Re-run just the sheet load and confirm it worked (paste into PowerShell):")
        L.append(f"       {rerun_command(group)}")
        L.append("   It ends with one line: SHEET LOAD: HEALTHY (fixed) or SHEET LOAD: FAILED with the reason.")
        L.append(f"   What you do yourself: {you}")
        L.append(f"   What the re-run does for you: {rerun}")
        L.append("")
    L.append("EVIDENCE")
    L.append(f"- Every try and its output: {evidence}" if evidence else "- (no evidence file was written)")
    L.append(f"- This text is also on your Desktop: {fcs.alert_paths()[-1]}")
    L.append("")
    L.append("This email goes to you only. No secret is in it: the key file is named by its path, never its contents.")
    subject = ("[TEST] " if test else "") + SUBJECT
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


def send(subject: str, body: str, today: date, now: datetime, mailer=None, state: Path | None = None, test: bool = False) -> str:
    """'sent', 'already sent at ...', 'not sent: ...'. At most one real alert a day; a test send is never counted."""
    if not test:
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
    if not test:
        try:
            state = Path(state or SENT_STATE)
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"date": today.isoformat(), "sent_at": now.isoformat(timespec="seconds"), "subject": subject}), encoding="utf-8")
        except Exception:                                                     # noqa: BLE001
            pass
    return "sent"


def hold_on(env: dict | None = None) -> bool:
    return ((os.environ if env is None else env).get(HOLD_VAR) or "").strip() == "1"


def alert(result: dict, context: str | None, config: Path, snapshots: Path, now: datetime, env: dict | None = None, mailer=None,
          qa_root: Path | None = None, state: Path | None = None, email: bool = True, alert_files=None) -> dict:
    """Evidence, the Desktop file and (once a day) the email. Returns {'evidence', 'files', 'email', 'subject', 'body', 'hold'}."""
    hold = hold_on(env)
    info = config_info(config)
    evidence = write_evidence({"context": context, "at": now.isoformat(timespec="seconds"), "hold": hold, **result}, now, qa_root)
    subject, body = compose(result, context, info, snapshots, hold, evidence, now.date())
    files = write_alert_file(body, alert_files)
    status = send(subject, body, now.date(), now, mailer, state) if email else "not sent: --once (you are at the keyboard)"
    return {"evidence": evidence, "files": files, "email": status, "subject": subject, "body": body, "hold": hold}


def verdict_line(result: dict, extra: str = "") -> str:
    n, f = len(result["clients"]), result["failed"]
    if not f:
        return f"SHEET LOAD: HEALTHY - {n} of {n} sheet(s) loaded" + (" (read only, nothing saved)" if result.get("read_only") else "") + extra
    causes = sorted({result["outcomes"][c]["cause"] for c in f})
    return f"SHEET LOAD: FAILED - {len(f)} of {n} sheet(s) did not load ({', '.join(f)}; cause: {', '.join(causes)})" + extra


# ------------------------------------------------------------------------------------------------ the guarded load (Friday, Saturday, the person's re-run)
def guarded_load(clients: list[str], context: str | None, config: Path | None = None, snapshots: Path | None = None, once: bool = False,
                 env: dict | None = None, mailer=None, sleep=time.sleep, runner=None, now=datetime.now, qa_root: Path | None = None,
                 state: Path | None = None, alert_files=None) -> tuple[int, dict, list[str]]:
    """(exit code, result, printed lines). Never raises."""
    config, snapshots = Path(config or CONFIG), Path(snapshots or SNAPSHOTS)
    try:
        result = load(clients, config, snapshots, waits=() if once else WAITS, sleep=sleep, runner=runner, now=now)
    except Exception as exc:                                                  # noqa: BLE001
        result = {"clients": list(clients), "failed": list(clients), "attempts": [], "read_only": False,
                  "outcomes": {c: {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "cause": "unknown", "at": now().isoformat(timespec="seconds")} for c in clients}}
    lines: list[str] = []
    if not result["failed"]:
        if alert_files is None:
            try:
                fcs.clear_alert()
            except Exception:                                                 # noqa: BLE001
                pass
        tries = len(result["attempts"])
        lines.append(verdict_line(result, f" at {now().strftime('%H:%M')}" + (f", on try {tries}" if tries > 1 else "")))
        return 0, result, lines
    a = alert(result, context, config, snapshots, now(), env, mailer, qa_root, state, email=not once, alert_files=alert_files)
    held = a["hold"] and not once
    lines.append(verdict_line(result, f"; email {a['email']}; evidence: {a['evidence']}" + (f"; RESEARCH HELD ({HOLD_VAR}=1)" if held else "")))
    if once:
        lines += ["", *a["body"].splitlines()]
    return (HELD_EXIT if held else 1), result, lines


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
            env: dict | None = None, mailer=None, qa_root: Path | None = None, state: Path | None = None,
            grace_s: int = DEADMAN_GRACE_S, poll_s: int = DEADMAN_POLL_S, alert_files=None) -> tuple[int, list[str]]:
    """Fetches nothing. Are today's copies there for the sheets this day's research takes? If not, the same CRITICAL email (once a day)."""
    snapshots, logs, config = Path(snapshots or SNAPSHOTS), Path(logs or LOGS), Path(config or CONFIG)
    _what, _task, clients = CONTEXTS[kind]
    t0 = now()
    today = t0.date()

    def stale() -> list[str]:
        out = []
        for c in clients:
            t = taken_at(newest_copy(c, snapshots))
            if not (t and t.date() == today):
                out.append(c)
        return out

    def running() -> bool:
        cut = now().timestamp() - 15 * 60
        return any(p.stat().st_mtime >= cut for p in todays_run_logs(today, logs))

    missing = stale()
    waited = 0
    # A research run that started late (the PC woke for this check and the 02:00 task caught up) is given time to take its copies.
    while missing and waited < grace_s and running():
        sleep(poll_s)
        waited += poll_s
        missing = stale()
    if not missing:
        return 0, [f"SHEET DEADMAN: HEALTHY - today's copies of all {len(clients)} sheet(s) for {kind} are there"]
    logs_today = todays_run_logs(today, logs)
    outcomes = {}
    for c in clients:
        if c not in missing:
            outcomes[c] = {"ok": True, "reason": "", "cause": None}
            continue
        cp = newest_copy(c, snapshots)
        cause = "never_ran"
        fl = next((ln for f in logs_today for ln in failures_in_log(f) if ln.startswith(f"{c}: FAILED - ")), None)
        if fl:
            reason = fl.split(": FAILED - ", 1)[1]
            cause = classify(reason)
        elif logs_today:
            reason = f"today's run log ({logs_today[-1].name}) exists but no copy of this sheet was taken today"
        else:
            reason = f"no run log for today in {logs} and no copy taken today"
        reason += f"; newest copy: {cp.name if cp else 'none'}"
        outcomes[c] = {"ok": False, "reason": reason, "cause": cause, "at": now().isoformat(timespec="seconds"), "tries": 1}
    result = {"clients": list(clients), "outcomes": outcomes, "failed": missing, "attempts": [], "read_only": True,
              "run_logs_today": [str(p) for p in logs_today]}
    a = alert(result, kind, config, snapshots, now(), env, mailer, qa_root, state, alert_files=alert_files)
    return 1, [f"SHEET DEADMAN: FAILED - {len(missing)} of {len(clients)} sheet(s) have no copy from today ({', '.join(missing)}); "
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
    ap.add_argument("--once", action="store_true", help="one try, no email: the person's re-run")
    ap.add_argument("--deadman", choices=[*sorted(CONTEXTS), "auto"], help="fetch nothing; are today's copies there? auto = by weekday (the 03:00 task)")
    ap.add_argument("--check-only", action="store_true", help="read-only: can every sheet be read now? (saves nothing, sends nothing)")
    ap.add_argument("--test-send", action="store_true", help="send ONE '[TEST] ...' email with a sample body")
    a = ap.parse_args(argv)
    config, snapshots = Path(a.config), Path(a.snapshots)
    try:
        if a.test_send:
            now = datetime.now()
            subj, body = compose(sample_result(now), "saturday", config_info(config), snapshots, hold_on(), None, now.date(), test=True)
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
            print(verdict_line(r))
            for ln in fix_summary(r, config):
                print("  - " + ln)
            return 0 if not r["failed"] else 1
        code, _r, lines = guarded_load(expand(a.clients, config), a.context, config, snapshots, once=a.once)
        print("\n".join(lines))
        return code
    except Exception as exc:                                                  # noqa: BLE001
        print(f"SHEET LOAD: DEGRADED - the check itself failed ({type(exc).__name__}: {exc})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
