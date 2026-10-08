"""ACT-61: the reviewer's patch for Markets/run_monthly.ps1 adds the Luna shadow step right after the existing shadow reader (Saturday only). Applied to a COPY of the live script."""
from pathlib import Path

from tests import test_shadow_reader_hook as H

P61 = H.ROOT / "docs" / "control" / "patches" / "ACT-61-run_monthly.ps1.patch"


def _copy(tmp_path):
    text = H.LIVE.read_text(encoding="utf-8")
    if "shadow_reader.py" not in text:
        text = H.apply_unified(text, H.P20.read_text(encoding="utf-8"))
    if "luna_shadow.py" not in text:
        text = H.apply_unified(text, P61.read_text(encoding="utf-8"))
    out = tmp_path / "run_monthly_patched.ps1"
    out.write_text(text.replace(H.LIVE_CFP, str(H.ROOT / "scripts")), encoding="utf-8")
    return out


def test_saturday_lists_luna_shadow_right_after_the_shadow_reader_with_its_caps(tmp_path):
    steps = H._list(_copy(tmp_path), "'Cybersecurity','Utility'")
    names = [Path(s[0]).name for s in steps]
    assert names.index("luna_shadow.py") == names.index("shadow_finder.py") + 1 == len(names) - 1 and names.index("shadow_reader.py") < names.index("shadow_finder.py")   # after the reader AND the finder, last
    s = steps[names.index("luna_shadow.py")]
    assert s[1:4] == ["--markets", "Cybersecurity", "Utility"] and "--max-minutes" in s and s[s.index("--token-budget") + 1] == "1500000" and "--run-log" in s
