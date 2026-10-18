"""scripts/live_build.py: the one sanctioned way code reaches the live build."""
from datetime import datetime

import scripts.live_build as lb


def _tree(base, files):
    for rel, text in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode())


def test_compare_ignores_line_endings_and_untouchable_files(tmp_path):
    repo, live = tmp_path / "repo", tmp_path / "live"
    _tree(repo, {"scripts/a.py": "x = 1\n", "scripts/b.py": "new\n", "scripts/run.bat": "echo repo\n",
                 "src/cfp_monitor/m.py": "m\n"})
    _tree(live, {"scripts/a.py": "x = 1\r\n", "scripts/b.py": "old\n", "scripts/run.bat": "echo live\n",
                 "scripts/only_live.py": "z\n", "src/cfp_monitor/m.py": "m\n"})
    c = lb.compare(repo, live)
    assert c["differ"] == ["scripts/b.py"]
    assert c["only_repo"] == []
    assert c["only_live"] == ["scripts/only_live.py"]
    assert c["bats"] == ["run.bat"]
    assert lb.drift_count(c) == 1


def test_release_dry_run_changes_nothing(tmp_path, monkeypatch):
    repo, live = tmp_path / "repo", tmp_path / "live"
    _tree(repo, {"scripts/b.py": "new\n"})
    _tree(live, {"scripts/b.py": "old\n"})
    monkeypatch.setattr(lb, "dirty_files", lambda files, repo=None: [])
    code, msg = lb.release(lb.compare(repo, live), apply=False, repo=repo, live=live)
    assert code == 0 and "DRY RUN" in msg
    assert (live / "scripts/b.py").read_text() == "old\n"


def test_release_refuses_uncommitted_files_and_running_tasks(tmp_path, monkeypatch):
    repo, live = tmp_path / "repo", tmp_path / "live"
    _tree(repo, {"scripts/b.py": "new\n"})
    _tree(live, {"scripts/b.py": "old\n"})
    monkeypatch.setattr(lb, "dirty_files", lambda files, repo=None: ["scripts/b.py"])
    code, msg = lb.release(lb.compare(repo, live), apply=True, repo=repo, live=live)
    assert code == 2 and "uncommitted" in msg
    monkeypatch.setattr(lb, "dirty_files", lambda files, repo=None: [])
    code, msg = lb.release(lb.compare(repo, live), apply=True, repo=repo, live=live,
                           running=lambda: ["CFP Weekly Re-Research (live markets)"])
    assert code == 2 and "running" in msg
    assert (live / "scripts/b.py").read_text() == "old\n"


def test_release_apply_backs_up_copies_and_logs(tmp_path, monkeypatch):
    repo, live = tmp_path / "repo", tmp_path / "live"
    _tree(repo, {"scripts/b.py": "new\n", "scripts/c.py": "c\n"})
    _tree(live, {"scripts/b.py": "old\n", "scripts/keep.db": "data"})
    monkeypatch.setattr(lb, "dirty_files", lambda files, repo=None: [])
    monkeypatch.setattr(lb, "git", lambda *a, repo=None: "abc1234")
    code, msg = lb.release(lb.compare(repo, live), apply=True, repo=repo, live=live,
                           running=lambda: [], now=datetime(2026, 10, 18, 9, 0, 0))
    assert code == 0
    assert (live / "scripts/b.py").read_text() == "new\n"
    assert (live / "scripts/c.py").read_text() == "c\n"
    assert (live / "_pre-release-20261018-090000/scripts/b.py").read_text() == "old\n"
    assert (live / "scripts/keep.db").read_text() == "data"
    log = (live / "RELEASE-LOG.md").read_text()
    assert "abc1234" in log and "scripts/b.py" in log and "scripts/c.py" in log
    assert lb.drift_count(lb.compare(repo, live)) == 0


def test_failed_check_rolls_the_release_back(tmp_path, monkeypatch):
    repo, live = tmp_path / "repo", tmp_path / "live"
    _tree(repo, {"scripts/b.py": "new\n", "scripts/c.py": "c\n"})
    _tree(live, {"scripts/b.py": "old\n"})
    monkeypatch.setattr(lb, "dirty_files", lambda files, repo=None: [])
    monkeypatch.setattr(lb, "git", lambda *a, repo=None: "abc1234")
    code, msg = lb.release(lb.compare(repo, live), apply=True, repo=repo, live=live,
                           running=lambda: [], check=lambda lv, rel: ["boom"],
                           now=datetime(2026, 10, 18, 9, 0, 0))
    assert code == 3 and "rolled back" in msg and "boom" in msg
    assert (live / "scripts/b.py").read_text() == "old\n"
    assert not (live / "scripts/c.py").exists()
    assert not (live / "RELEASE-LOG.md").exists()


def test_smoke_catches_a_syntax_error_and_a_failing_import(tmp_path):
    import sys
    live = tmp_path / "live"
    _tree(live, {"scripts/__init__.py": "", "scripts/good.py": "x = 1\n",
                 "scripts/bad.py": "def (:\n"})
    problems = lb.smoke(live, ["scripts/good.py", "scripts/bad.py"], python=sys.executable)
    assert any("does not parse" in p and "bad.py" in p for p in problems)
    assert not any("good.py" in p for p in problems)


def test_smoke_passes_clean_code_but_reports_a_missing_sunday_module(tmp_path):
    import sys
    live = tmp_path / "live"
    _tree(live, {"scripts/__init__.py": "", "scripts/good.py": "x = 1\n"})
    problems = lb.smoke(live, ["scripts/good.py"], python=sys.executable)
    assert not any("does not parse" in p for p in problems)
    assert any("scripts.weekly_verify" in p for p in problems)
