"""verify_grounding.py --apply must not rewrite the whole database by accident (2026-10-03: 426 rows re-verified, 13 changed)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_apply_without_market_is_refused_and_touches_nothing(tmp_path):
    db = tmp_path / "never_created.db"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_grounding.py"), "--db", str(db), "--apply"], capture_output=True, text=True)
    assert p.returncode == 2 and "REFUSED" in p.stderr and not db.exists()
