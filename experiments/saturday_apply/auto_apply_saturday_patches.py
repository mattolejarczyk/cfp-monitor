"""Unattended version of the Saturday patches apply (ACT-64, ACT-63, ACT-22): meant to run every 30 minutes on Friday from a one-time scheduled task.

Each run does ONE of these and then exits:
  - all patches already in             -> says so by e-mail ONCE, then stays silent
  - the window has closed (Sat 01:00)   -> ONE final e-mail: not applied, Saturday runs the old way, apply it after Saturday's run
  - a CFP task is running (Friday's awards run still going) -> waits; an e-mail reminder every 4th wait (about 2 hours), saying what is running
  - otherwise                           -> runs apply_saturday_patches.py --apply (backups, parse check, byte-for-byte read-back, automatic restore) and e-mails the result
Any other refusal (a patch that no longer fits, a parse error) is e-mailed once per distinct message and nothing is changed.
E-mail goes to the operator only (CFP_RECAP_TO). State lives in %LOCALAPPDATA%\\CFP-Monitor\\runs_out\\saturday_apply_state.json.
    --dry-run   prints what it would do, sends nothing, writes nothing (also runs the wrapper in its own dry-run mode)
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\Users\matts\cfp-monitor")
import apply_saturday_patches as base  # noqa: E402

PY = r"C:\Users\matts\cfp-monitor\.venv\Scripts\python.exe"
WRAPPER = HERE / "apply_saturday_patches.py"
STATE = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\matts\AppData\Local")) / "CFP-Monitor" / "runs_out" / "saturday_apply_state.json"
WINDOW_CLOSES = dt.datetime(2026, 10, 17, 1, 0)      # Saturday 01:00: the 02:00 research job is about to start
REMIND_EVERY = 4                                     # waits (30 minutes each) between reminders


def load_state(path=STATE):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"attempts": 0, "waits": 0, "sent": []}


def save_state(s, path=STATE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(s, indent=1), encoding="utf-8")


def default_mailer(subject, body):
    sys.path.insert(0, r"C:\Users\matts\cfp-monitor")
    from src.cfp_monitor.alerts import maybe_send_email
    return maybe_send_email(subject, body, to_env="CFP_RECAP_TO")


def both_applied(markets):
    for t in base.TARGETS:
        raw = (Path(markets) / t["file"]).read_bytes()
        if t["present"].encode("utf-8") not in raw:
            return False
    return True


def run_wrapper(markets, apply):
    cmd = [PY, str(WRAPPER)] + (["--apply"] if apply else []) + ["--markets-dir", str(markets)]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def once(markets, now, dry, mailer, state_path=STATE, runner=run_wrapper, applied=both_applied):
    s = load_state(state_path)
    sent = set(s.get("sent", []))
    actions = []

    def say(key, subject, body):
        if key in sent and not key.startswith("remind"):
            return
        actions.append(subject)
        if dry:
            print(f"[dry run] would e-mail: {subject}\n{body}\n")
        else:
            ok = mailer(subject, body)
            print(f"e-mail {'sent' if ok else 'NOT sent (mail settings missing)'}: {subject}")
            sent.add(key)

    if applied(markets):
        if "applied" not in sent:
            say("done-already", "CFP Saturday patches: all are in the Markets scripts", "ACT-64 (sponsor prefill), ACT-63 (new events) and ACT-22 (Friday awards shadow step) are all in run_overnight.ps1 and run_monthly.ps1. Nothing more to do. Saturday 02:00 uses ACT-64 and ACT-63; the awards shadow step first runs next Friday.")
    elif now >= WINDOW_CLOSES:
        say("window-closed", "CFP Saturday patches: NOT applied, the window has closed",
            "The Saturday patches (ACT-64 sponsor prefill, ACT-63 new events, ACT-22 Friday awards shadow step) were not applied before Saturday 01:00, so Saturday 02:00 runs the old way (nothing breaks, it just costs more and new events load by hand). Apply them after Saturday's run: python experiments\\saturday_apply\\apply_saturday_patches.py, then again with --apply. Tell Claude.")
    else:
        code, out = runner(markets, apply=not dry)
        s["attempts"] = s.get("attempts", 0) + 1
        text = out.strip()
        if "DONE." in out or ("DRY RUN OK" in out and dry):
            say("applied", "CFP Saturday patches APPLIED: ACT-64, ACT-63 and ACT-22 are in", "All three patches were applied automatically and verified (backup, read-back, parse check).\n\n" + text[-1500:] + "\n\nTell Claude and it re-verifies. Undo = copy the *.pre-act64-20261013 / *.pre-act63-20261013 backups over the scripts.")
        elif "a CFP task is running" in out:
            s["waits"] = s.get("waits", 0) + 1
            if s["waits"] % REMIND_EVERY == 0:
                say("remind-%d" % s["waits"], "CFP Saturday patches: still waiting for Friday's run to finish",
                    "The Saturday patches are NOT applied yet because a CFP task is still running (so the scripts cannot be changed safely). I will keep trying every 30 minutes until Saturday 01:00 and e-mail the moment they are in.\n\n" + text[-600:])
        elif "already applied" in out and "Nothing to apply" in out:
            say("done-already", "CFP Saturday patches: all are in the Markets scripts", "All the patches are already in. Nothing more to do.")
        else:
            key = "stop-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
            say(key, "CFP Saturday patches: NOT applied - needs a look", "The automatic apply stopped and changed nothing (or restored its backup):\n\n" + text[-1800:] + "\n\nTell Claude; run python experiments\\saturday_apply\\apply_saturday_patches.py to see the same result.")
    if not dry:
        s["sent"] = sorted(sent)
        s["last_run"] = now.isoformat(timespec="seconds")
        save_state(s, state_path)
    return actions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--markets-dir", default=str(base.LIVE_MARKETS))
    ap.add_argument("--now", default="", help="ISO time, for rehearsal")
    ap.add_argument("--state", default=str(STATE), help="state file (a rehearsal uses its own)")
    ap.add_argument("--no-mail", action="store_true", help="print the e-mails instead of sending them (rehearsal)")
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.now) if a.now else dt.datetime.now()
    def print_mailer(subject, body):
        print(f"[no-mail] {subject}")
        print(body)
        return True

    mailer = print_mailer if a.no_mail else default_mailer
    acts = once(a.markets_dir, now, a.dry_run, mailer, state_path=a.state)
    print(f"{now:%Y-%m-%d %H:%M}: " + ("; ".join(acts) if acts else "nothing to report this time"))


if __name__ == "__main__":
    main()
