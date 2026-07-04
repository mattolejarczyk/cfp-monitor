"""Run every test_*.py in this folder; exit non-zero if any fails."""
import glob, os, subprocess, sys

here = os.path.dirname(__file__)
bad = 0
for f in sorted(glob.glob(os.path.join(here, "test_*.py"))):
    r = subprocess.run([sys.executable, f], capture_output=True, text=True)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"
    print(f"{os.path.basename(f):26} {last}")
    if r.returncode:
        bad += 1
        print(r.stdout[-800:]); print(r.stderr[-400:])
print(f"=== {'ALL PASS' if not bad else str(bad)+' FILE(S) FAILED'} ===")
sys.exit(1 if bad else 0)
