"""Where the repo and the live build stand, and the one sanctioned way to move code across.

WHY THIS EXISTS
There are two folders. The repo (cfp-monitor) is where code is written and tested. The live
build (AppData\\Local\\CFP-Monitor) is the installation: it holds the real database and the
customer app and has its own Python. Nothing ever recorded how far apart they were, and by
2026-10-18 they differed in 84 files with nobody having decided that. HANDOFF 2026-09-27 asked
for exactly this deploy step.

    python scripts/live_build.py status            read only: how many files differ, and which
    python scripts/live_build.py rehearse          the release into a SCRATCH copy of the live
                                                   build, tested with the live build's own Python
    python scripts/live_build.py release           DRY RUN: what a release would copy
    python scripts/live_build.py release --apply   back up, copy, test, log; rolls back on failure
    python scripts/live_build.py rollback <stamp>  put back the files a release overwrote

RULES
- Only code moves: scripts/*.py and src/cfp_monitor/*.py. The database, the venv, the .bat
  entry points and anything that exists only in the live build are never touched. A .bat that
  differs is REPORTED, not copied (the live one carries local settings).
- Line endings are ignored when comparing (git may store LF where Windows holds CRLF).
- `release --apply` refuses to run while a CFP scheduled task is running, and it refuses to copy
  a repo file that has uncommitted edits: what runs overnight must be what is on GitHub.
- After copying, the release is TESTED WITH THE LIVE BUILD'S OWN PYTHON (venv\\Scripts\\python.exe):
  every released file must parse, the modules the Sunday job imports must import, and
  check_invariants.py must run on the live database. Any failure rolls the release back at once.
  This exists because on 2026-08-12 (JUDGEMENT.md section 13) copying new scripts onto an old live
  build would have died at import, unattended, at 01:00.
- Passing here does not replace one real run under the scheduled task: clone the registered task
  with a one-time trigger and read its log (a rehearsal cannot find a bug in how the task runs).
- Every release writes RELEASE-LOG.md in the live build: when, the git commit, and each file.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor")
CODE_GLOBS = ("scripts/*.py", "src/cfp_monitor/*.py")
SKIP_PARTS = ("__pycache__",)
# Imported by the Sunday job; if any of these cannot be imported the 01:00 run dies unattended.
SUNDAY_MODULES = ("scripts.weekly_verify", "scripts.verify_grounding", "scripts.check_invariants",
                  "scripts.weekend_recap", "scripts.recheck_dead_links")

PARSE_TEST = (
    "import ast, sys\n"
    "bad = []\n"
    "for f in sys.argv[1:]:\n"
    "    try:\n"
    "        ast.parse(open(f, encoding='utf-8-sig').read(), f)\n"
    "    except SyntaxError as e:\n"
    "        bad.append(f + ': ' + str(e))\n"
    "print(chr(10).join(bad))\n"
)
IMPORT_TEST = (
    "import importlib, sys\n"
    "sys.path.insert(0, '.')\n"
    "bad = []\n"
    "for m in sys.argv[1:]:\n"
    "    try:\n"
    "        importlib.import_module(m)\n"
    "    except BaseException as e:\n"
    "        bad.append(m + ': ' + type(e).__name__ + ': ' + str(e)[:200])\n"
    "print(chr(10).join(bad))\n"
)


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def code_files(base: Path) -> dict[str, Path]:
    out = {}
    for pat in CODE_GLOBS:
        for p in sorted(base.glob(pat)):
            if p.is_file() and not any(s in p.parts for s in SKIP_PARTS):
                out[p.relative_to(base).as_posix()] = p
    return out


def compare(repo: Path = ROOT, live: Path = LIVE) -> dict:
    r, l = code_files(repo), code_files(live)
    differ = [k for k in r if k in l and _norm(r[k].read_bytes()) != _norm(l[k].read_bytes())]
    only_repo = [k for k in r if k not in l]
    only_live = [k for k in l if k not in r]
    bats = []
    for p in sorted((repo / "scripts").glob("*.bat")):
        q = live / "scripts" / p.name
        if q.exists() and _norm(p.read_bytes()) != _norm(q.read_bytes()):
            bats.append(p.name)
    return {"differ": differ, "only_repo": only_repo, "only_live": only_live, "bats": bats}


def drift_count(cmp: dict) -> int:
    """Files a release would copy."""
    return len(cmp["differ"]) + len(cmp["only_repo"])


def git(*args: str, repo: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True).stdout.strip()


def dirty_files(files: list[str], repo: Path = ROOT) -> list[str]:
    """Repo files in `files` with uncommitted edits, or never committed."""
    if not files:
        return []
    out = git("status", "--porcelain", "--", *files, repo=repo)
    return sorted({line[3:].strip().strip('"') for line in out.splitlines() if line.strip()})


def cfp_task_running() -> list[str]:
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-ScheduledTask | Where-Object { $_.TaskName -like 'CFP*' -and $_.State -eq 'Running' } "
             "| ForEach-Object { $_.TaskName }"], capture_output=True, text=True, timeout=60)
        return [x.strip() for x in res.stdout.splitlines() if x.strip()]
    except Exception:
        return []


def live_python(live: Path = LIVE) -> Path:
    return live / "venv" / "Scripts" / "python.exe"


def smoke(live: Path, released: list[str], python: Path | None = None,
          db: Path | None = None, seed_dir: Path | None = None) -> list[str]:
    """Problems found when the released code is run by the LIVE build's own interpreter."""
    py = str(python or live_python(live))
    problems: list[str] = []
    files = [str(live / k) for k in released]
    r = subprocess.run([py, "-c", PARSE_TEST, *files], cwd=str(live), capture_output=True, text=True)
    if r.returncode != 0:
        return ["the live Python could not run at all: " + (r.stderr or r.stdout).strip()[-300:]]
    problems += ["does not parse under the live Python: " + x for x in r.stdout.strip().splitlines() if x]
    mods = list(SUNDAY_MODULES) + sorted(
        "src.cfp_monitor." + Path(k).stem for k in released if k.startswith("src/cfp_monitor/"))
    r = subprocess.run([py, "-c", IMPORT_TEST, *mods], cwd=str(live), capture_output=True, text=True)
    if r.stdout.strip():
        problems += ["does not import under the live Python: " + x for x in r.stdout.strip().splitlines()]
    elif r.returncode != 0:
        problems.append("the import test crashed: " + (r.stderr or "").strip()[-300:])
    if db is not None:
        cmd = [py, "scripts/check_invariants.py", "--db", str(db)]
        if seed_dir is not None:
            cmd += ["--seed-dir", str(seed_dir)]
        r = subprocess.run(cmd, cwd=str(live), capture_output=True, text=True,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode != 0:
            problems.append("check_invariants.py failed under the live Python: "
                            + (r.stdout + r.stderr).strip()[-400:])
    return problems


def rollback(live: Path, stamp: str, added: list[str] | None = None) -> str:
    """Put back what release `stamp` overwrote; remove what it added (when named)."""
    bk = live / f"_pre-release-{stamp}"
    if not bk.is_dir():
        return f"No backup folder {bk.name} in {live}."
    n = 0
    for src in sorted(p for p in bk.rglob("*") if p.is_file()):
        shutil.copy2(src, live / src.relative_to(bk))
        n += 1
    removed = 0
    for k in added or []:
        try:
            (live / k).unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return f"Rolled back: restored {n} file(s), removed {removed} added file(s)."


def report(cmp: dict) -> str:
    L = [f"Live build vs repo: {drift_count(cmp)} file(s) a release would copy "
         f"({len(cmp['differ'])} older in live, {len(cmp['only_repo'])} missing from live).",
         f"Only in the live build (never touched): {len(cmp['only_live'])}."]
    if cmp["bats"]:
        L.append("Entry points that differ (never copied, check by hand): " + ", ".join(cmp["bats"]))
    for title, key in (("older in live", "differ"), ("missing from live", "only_repo")):
        if cmp[key]:
            L.append(f"\n{title}:")
            L += [f"  {k}" for k in cmp[key]]
    return "\n".join(L)


def release(cmp: dict, apply: bool, repo: Path = ROOT, live: Path = LIVE,
            running=cfp_task_running, now: datetime | None = None, check=None,
            allow_dirty: bool = False) -> tuple[int, str]:
    """`check(live, todo)` returns problems found after the copy; any problem rolls the release back."""
    todo = cmp["differ"] + cmp["only_repo"]
    if not todo:
        return 0, "Nothing to release: the live build already matches the repo."
    dirty = [] if allow_dirty else dirty_files(todo, repo)
    if dirty:
        return 2, ("Refusing: these repo files have uncommitted edits. Commit and push first, "
                   "so the live build matches GitHub:\n  " + "\n  ".join(dirty))
    if not apply:
        return 0, f"DRY RUN: a release would copy {len(todo)} file(s). Re-run with --apply.\n" + \
            "\n".join("  " + k for k in todo)
    busy = running()
    if busy:
        return 2, "Refusing: a CFP task is running: " + ", ".join(busy)
    now = now or datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    bk = live / f"_pre-release-{stamp}"
    for k in todo:
        dst = live / k
        if dst.exists():
            (bk / k).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, bk / k)
    for k in todo:
        dst = live / k
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / k, dst)
    problems = check(live, todo) if check else []
    if problems:
        msg = rollback(live, stamp, cmp["only_repo"])
        return 3, ("Release FAILED its test with the live Python and was rolled back. " + msg
                   + "\n  " + "\n  ".join(problems))
    commit = git("rev-parse", "--short", "HEAD", repo=repo)
    with open(live / "RELEASE-LOG.md", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"\n## {now:%Y-%m-%d %H:%M} release of commit {commit}\n\n"
                 f"Backup of overwritten files: {bk.name}\n\n" + "".join(f"- {k}\n" for k in todo))
    after = compare(repo, live)
    return 0, (f"Released {len(todo)} file(s) from commit {commit}, tested with the live Python. "
               f"Backup: {bk}. To undo: python scripts/live_build.py rollback {stamp}. "
               f"Still differing afterwards: {drift_count(after)}.")


def rehearse(scratch: Path, repo: Path = ROOT, live: Path = LIVE) -> tuple[int, str]:
    """The release, done into a scratch copy of the live build's code and data, tested with the
    REAL live Python. Nothing in the live build is touched."""
    if scratch.exists():
        shutil.rmtree(scratch)
    for sub in ("scripts", "src", "market_sheets"):
        if (live / sub).is_dir():
            shutil.copytree(live / sub, scratch / sub, ignore=shutil.ignore_patterns("__pycache__"))
    src = sqlite3.connect(f"file:{(live / 'cfp_monitor.db').as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(scratch / "cfp_monitor.db"))
    src.backup(dst)
    dst.close()
    src.close()
    py = live_python(live)
    db, seeds = scratch / "cfp_monitor.db", scratch / "market_sheets"
    code, msg = release(compare(repo, scratch), True, repo=repo, live=scratch, running=lambda: [],
                        check=lambda lv, rel: smoke(lv, rel, py, db, seeds), allow_dirty=True)
    return code, f"REHEARSAL in {scratch} (the live build was not touched).\n{msg}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "release", "rehearse", "rollback"])
    ap.add_argument("stamp", nargs="?", help="rollback: the stamp printed by the release")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--live", default=str(LIVE), help="the live build folder (default: the real one)")
    ap.add_argument("--scratch", default=str(Path(os.environ.get("TEMP", ".")) / "live_build_rehearsal"),
                    help="outside the repo on purpose: it holds a copy of the database")
    a = ap.parse_args()
    live = Path(a.live)
    if a.command == "rollback":
        if not a.stamp:
            print("rollback needs the stamp, e.g. 20261018-090000")
            return 2
        print(rollback(live, a.stamp))
        return 0
    if a.command == "rehearse":
        code, msg = rehearse(Path(a.scratch), live=live)
        print(msg)
        return code
    cmp = compare(ROOT, live)
    if a.command == "status":
        print(report(cmp))
        return 0
    py = live_python(live)
    code, msg = release(cmp, a.apply, live=live,
                        check=lambda lv, rel: smoke(lv, rel, py, lv / "cfp_monitor.db", lv / "market_sheets"))
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
