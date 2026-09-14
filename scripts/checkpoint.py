"""One labelled checkpoint across every CFP code base, and a coordinated way back.

    python scripts/checkpoint.py create  --label known-good-2026-09-14 [--note "..."]
    python scripts/checkpoint.py list
    python scripts/checkpoint.py verify  --label known-good-2026-09-14
    python scripts/checkpoint.py restore --label known-good-2026-09-14 [--apply] [--repos Markets]

WHY. The pipeline is three git repos plus a copy of the app that is not in git at all:

    cfp-monitor    the gate, the loop, the page builder        git
    Markets        the research run, prompts, deliveries       git (deliveries are gitignored)
    handoff-files  the contract and every hand-back            git
    <LOCALAPPDATA>\\CFP-Monitor  the build the Sunday job runs, its DB and seeds   NOT git

A change usually lands in two of them at once - a rule in Markets, its guard in cfp-monitor, the
amendment in handoff-files - so reverting one alone leaves the pipeline internally inconsistent:
the gate enforcing a rule the generator no longer follows, or an amendment describing behaviour
no code has. A checkpoint records all four together, and restore walks them in one planned pass.

HOW RESTORE WORKS, AND WHAT IT WILL NOT DO
Restore REVERTS FORWARD (`git revert <tag>..HEAD`): history is kept and the revert is itself
revertible. It never resets, never force-pushes, never touches a repo with uncommitted work, and
never restores the live database on its own - a DB is state, not code, and the manifest's copy is
a point in time that may be older than rows imported since. It prints those steps instead.

It cannot be atomic across four systems. So it is PLANNED, then applied in a fixed order, and if
a repo fails the run STOPS and prints exactly which repos were reverted, which were not, and the
one command that undoes each completed step. The failure mode to avoid is not "a repo fails" -
it is not knowing afterwards which ones did.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = Path(r"C:\Users\matts\CFP-KnownGood")
LIVE = Path(r"C:\Users\matts\AppData\Local\CFP-Monitor")
MARKETS = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets")
HANDOFF = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\handoff-files")

# Restore order: the contract first (it is only text and explains the rest), then the generator,
# then the code that judges it. Reverting the gate before the generator would briefly enforce
# old rules against new rows.
REPOS: dict[str, Path] = {"handoff-files": HANDOFF, "Markets": MARKETS, "cfp-monitor": ROOT}
LIVE_COPY = ("scripts", "src", "market_sheets", "docs", "tests")
LIVE_FILES = ("pyproject.toml", "uv.lock", "run.py", "app.py", "CFP-Monitor.bat", "README.md",
              "HANDOFF.md", "customer_sheets.json")
DELIVERIES = ("Cybersecurity_audited.final.csv", "Utility_audited.final.csv")


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo.name}:\n{r.stderr.strip()}")
    return r.stdout.strip()


def dirty(repo: Path) -> list[str]:
    return [ln for ln in git(repo, "status", "--porcelain").splitlines()
            if not ln.startswith("??")]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------ create
def create(label: str, note: str, repos: dict[str, Path], store: Path, live: Path | None) -> int:
    blocked = {n: dirty(p) for n, p in repos.items() if dirty(p)}
    if blocked:
        for n, lines in blocked.items():
            print(f"  {n}: {len(lines)} uncommitted change(s)")
            print("\n".join(f"      {ln}" for ln in lines[:5]))
        print("\nCommit or stash first: a checkpoint must name a state that exists in history.")
        return 1

    dest = store / label
    if dest.exists():
        print(f"{dest} already exists - pick another label.")
        return 1

    manifest = {"label": label, "note": note, "created": datetime.now().isoformat(timespec="seconds"),
                "repos": {}, "live_build": {}, "deliveries": {}}
    for name, path in repos.items():
        manifest["repos"][name] = {"path": str(path), "branch": git(path, "rev-parse", "--abbrev-ref", "HEAD"),
                                   "commit": git(path, "rev-parse", "HEAD")}
    # The tag message carries the SIBLING commits, so a repo cloned alone still says what it
    # belonged with.
    siblings = "; ".join(f"{n}@{d['commit'][:9]}" for n, d in manifest["repos"].items())
    for name, path in repos.items():
        git(path, "tag", "-a", label, "-m", f"{note or 'checkpoint'} | {siblings}")
        push = subprocess.run(["git", "-C", str(path), "push", "origin", label],
                              capture_output=True, text=True)
        manifest["repos"][name]["pushed"] = push.returncode == 0
        print(f"  tagged {name} {manifest['repos'][name]['commit'][:9]}"
              f"{' (pushed)' if push.returncode == 0 else ' (LOCAL ONLY)'}")

    dest.mkdir(parents=True)
    if live and live.exists():
        lb = dest / "live-build"
        for d in LIVE_COPY:
            if (live / d).exists():
                shutil.copytree(live / d, lb / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for f in LIVE_FILES:
            if (live / f).exists():
                shutil.copy2(live / f, lb / f)
        db = live / "cfp_monitor.db"
        if db.exists():                      # SQLite's own backup: consistent even if it is open
            src, dst = sqlite3.connect(db), sqlite3.connect(lb / "cfp_monitor.db")
            src.backup(dst)
            dst.close()
            src.close()
        manifest["live_build"] = {str(p.relative_to(lb)): sha256(p)
                                  for p in sorted(lb.rglob("*")) if p.is_file()}
        print(f"  live build snapshot: {len(manifest['live_build'])} file(s)")
    dl = dest / "deliveries"
    dl.mkdir()
    for name in DELIVERIES:
        src = MARKETS / name
        if src.exists():
            shutil.copy2(src, dl / name)
            manifest["deliveries"][name] = sha256(src)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\ncheckpoint '{label}' -> {dest}")
    return 0


# ------------------------------------------------------------------------------ verify
def load(label: str, store: Path) -> dict:
    p = store / label / "manifest.json"
    if not p.exists():
        raise SystemExit(f"no checkpoint '{label}' in {store}")
    return json.loads(p.read_text(encoding="utf-8"))


def verify(label: str, store: Path) -> int:
    m = load(label, store)
    print(f"checkpoint '{label}' taken {m['created']}" + (f" - {m['note']}" if m.get("note") else ""))
    drift = 0
    print("\n| repo | at checkpoint | now | commits since | uncommitted |")
    print("|---|---|---|---|---|")
    for name, d in m["repos"].items():
        path = Path(d["path"])
        if not path.exists():
            print(f"| {name} | {d['commit'][:9]} | MISSING | - | - |")
            drift += 1
            continue
        head = git(path, "rev-parse", "HEAD")
        ahead = git(path, "rev-list", "--count", f"{d['commit']}..HEAD", check=False) or "?"
        wip = len(dirty(path))
        print(f"| {name} | {d['commit'][:9]} | {head[:9]} | {ahead} | {wip} |")
        drift += (head != d["commit"])
    lb = store / label / "live-build"
    if m.get("live_build"):
        changed = [rel for rel, h in m["live_build"].items()
                   if rel != "cfp_monitor.db"
                   and (not (LIVE / rel).exists() or sha256(LIVE / rel) != h)]
        print(f"\nlive build: {len(m['live_build'])} file(s) recorded, {len(changed)} changed since")
        for rel in changed[:10]:
            print(f"    {rel}")
        print("    (cfp_monitor.db always differs - it is state; judge it with check_invariants.py)")
    print(f"\n{'IN SYNC with the checkpoint' if not drift else f'{drift} repo(s) have moved'}")
    return 0


# ------------------------------------------------------------------------------ restore
def plan_restore(label: str, store: Path, only: list[str] | None) -> tuple[list[tuple], list[str]]:
    m = load(label, store)
    plan, blockers = [], []
    for name, d in m["repos"].items():
        if only and name not in only:
            continue
        path = Path(d["path"])
        if not path.exists():
            blockers.append(f"{name}: path missing ({path})")
            continue
        if dirty(path):
            blockers.append(f"{name}: uncommitted work - commit or stash before restoring")
            continue
        if git(path, "cat-file", "-t", d["commit"], check=False) != "commit":
            blockers.append(f"{name}: commit {d['commit'][:9]} not in this clone - fetch first")
            continue
        n = git(path, "rev-list", "--count", f"{d['commit']}..HEAD")
        commits = git(path, "log", "--oneline", f"{d['commit']}..HEAD")
        plan.append((name, path, d["commit"], int(n or 0), commits))
    return plan, blockers


def restore(label: str, store: Path, only: list[str] | None, apply: bool) -> int:
    plan, blockers = plan_restore(label, store, only)
    for b in blockers:
        print(f"  BLOCKED {b}")
    if blockers:
        print("\nNothing was changed. Clear the blockers above and re-run.")
        return 1
    print(f"Restore to '{label}' - reverting forward, history kept:\n")
    for name, _p, commit, n, commits in plan:
        print(f"  {name}: {n} commit(s) to revert, back to {commit[:9]}")
        for ln in commits.splitlines()[:6]:
            print(f"      {ln}")
    if not any(n for _a, _b, _c, n, _d in plan):
        print("\nEverything is already at the checkpoint. Nothing to do.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing changed. Re-run with --apply to perform it.")
        return 0

    done: list[tuple[str, Path, str]] = []
    for name, path, commit, n, _c in plan:
        if not n:
            continue
        before = git(path, "rev-parse", "HEAD")
        r = subprocess.run(["git", "-C", str(path), "revert", "--no-edit", f"{commit}..HEAD"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "-C", str(path), "revert", "--abort"], capture_output=True)
            print(f"\n  FAILED on {name}: {r.stderr.strip()[:300]}")
            print("\nSTOPPED. State right now:")
            for dn, dp, db_ in done:
                print(f"  REVERTED {dn} (undo with:  git -C {dp} reset --hard {db_})")
            print(f"  FAILED   {name} - unchanged")
            for rest in plan[plan.index((name, path, commit, n, _c)) + 1:]:
                print(f"  NOT TOUCHED {rest[0]}")
            return 1
        done.append((name, path, before))
        print(f"  reverted {name} ({n} commit(s))")
    print("\nRestored. Push when you are satisfied:")
    for name, path, _b in done:
        print(f"  git -C {path} push")
    print("\nThe live build and database were NOT touched. If the code you just reverted had "
          "changed them, restore those deliberately:")
    print(f"  copy the snapshot from {store / label / 'live-build'} and run check_invariants.py")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("create", "list", "verify", "restore"))
    ap.add_argument("--label")
    ap.add_argument("--note", default="")
    ap.add_argument("--store", default=str(STORE))
    ap.add_argument("--repos", help="comma-separated subset, for restore")
    ap.add_argument("--apply", action="store_true", help="restore: actually do it")
    ap.add_argument("--no-live", action="store_true", help="create: skip the live-build snapshot")
    a = ap.parse_args()
    store = Path(a.store)

    if a.action == "list":
        for p in sorted(store.glob("*/manifest.json")):
            m = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {m['label']:28} {m['created']}  {m.get('note', '')[:60]}")
            print("      " + ", ".join(f"{n}@{d['commit'][:9]}" for n, d in m["repos"].items()))
        return 0
    if not a.label:
        return ap.error("--label is required")
    if a.action == "create":
        return create(a.label, a.note, REPOS, store, None if a.no_live else LIVE)
    if a.action == "verify":
        return verify(a.label, store)
    return restore(a.label, store, a.repos.split(",") if a.repos else None, a.apply)


if __name__ == "__main__":
    sys.exit(main())
