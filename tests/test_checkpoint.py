"""Coordinated checkpoint and rollback across the CFP code bases, on throwaway repos.

The failure this guards against is not "a repo fails to revert" - it is finishing a multi-repo
rollback without knowing which repos moved. So the tests pin: a checkpoint refuses dirty repos,
verify reports drift per repo, restore is a dry run by default, and a mid-way failure stops and
names what was reverted, what failed and what was never touched.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import checkpoint as cp                                  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def make_repo(path: Path, name: str) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    (path / "f.txt").write_text(f"{name} v1\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-qm", f"{name} first")
    return path


@pytest.fixture
def repos(tmp_path):
    return {n: make_repo(tmp_path / n, n) for n in ("alpha", "beta")}


def commit(repo: Path, text: str, msg: str):
    (repo / "f.txt").write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


def test_create_refuses_when_a_repo_has_uncommitted_work(repos, tmp_path, capsys):
    (repos["beta"] / "f.txt").write_text("edited, not committed\n", encoding="utf-8")
    assert cp.create("cp1", "", repos, tmp_path / "store", None) == 1
    assert "uncommitted" in capsys.readouterr().out
    assert not (tmp_path / "store" / "cp1").exists()


def test_create_tags_every_repo_and_records_its_siblings(repos, tmp_path):
    assert cp.create("cp1", "before the change", repos, tmp_path / "store", None) == 0
    m = json.loads((tmp_path / "store" / "cp1" / "manifest.json").read_text(encoding="utf-8"))
    assert set(m["repos"]) == {"alpha", "beta"}
    for name, path in repos.items():
        assert git(path, "rev-parse", "HEAD") == m["repos"][name]["commit"]
        # the tag names what it belonged with, so a repo read alone still says so
        assert "beta@" in git(path, "tag", "-n99", "cp1")


def test_verify_reports_which_repo_moved(repos, tmp_path, capsys):
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    cp.verify("cp1", tmp_path / "store")
    out = capsys.readouterr().out
    assert "1 repo(s) have moved" in out


def test_restore_is_a_dry_run_by_default(repos, tmp_path, capsys):
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    assert cp.restore("cp1", tmp_path / "store", None, apply=False) == 0
    assert "DRY RUN" in capsys.readouterr().out
    assert (repos["alpha"] / "f.txt").read_text(encoding="utf-8") == "alpha v2\n"


def test_restore_reverts_forward_and_keeps_history(repos, tmp_path):
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    commit(repos["beta"], "beta v2\n", "beta change")
    assert cp.restore("cp1", tmp_path / "store", None, apply=True) == 0
    for name, path in repos.items():
        assert (path / "f.txt").read_text(encoding="utf-8") == f"{name} v1\n"
        # reverted forward: the change and its revert are both still in the log
        assert "change" in git(path, "log", "--oneline")
        assert len(git(path, "log", "--oneline").splitlines()) == 3


def test_restore_can_be_scoped_to_one_repo(repos, tmp_path):
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    commit(repos["beta"], "beta v2\n", "beta change")
    cp.restore("cp1", tmp_path / "store", ["beta"], apply=True)
    assert (repos["alpha"] / "f.txt").read_text(encoding="utf-8") == "alpha v2\n"
    assert (repos["beta"] / "f.txt").read_text(encoding="utf-8") == "beta v1\n"


def test_a_dirty_repo_blocks_the_whole_restore_before_anything_changes(repos, tmp_path, capsys):
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    commit(repos["beta"], "beta v2\n", "beta change")
    (repos["beta"] / "f.txt").write_text("beta v2 edited\n", encoding="utf-8")
    assert cp.restore("cp1", tmp_path / "store", None, apply=True) == 1
    out = capsys.readouterr().out
    assert "BLOCKED" in out and "Nothing was changed" in out
    assert (repos["alpha"] / "f.txt").read_text(encoding="utf-8") == "alpha v2\n"


def test_a_failure_midway_stops_and_names_what_moved(repos, tmp_path, capsys, monkeypatch):
    """The whole point: after a partial rollback you must know exactly where you are."""
    cp.create("cp1", "", repos, tmp_path / "store", None)
    commit(repos["alpha"], "alpha v2\n", "alpha change")
    commit(repos["beta"], "beta v2\n", "beta change")
    real = subprocess.run

    def fail_on_beta(cmd, *a, **kw):
        if "revert" in cmd and str(repos["beta"]) in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "conflict in f.txt")
        return real(cmd, *a, **kw)
    monkeypatch.setattr(cp.subprocess, "run", fail_on_beta)

    # handoff-files, Markets, cfp-monitor order maps to alphabetical here: alpha then beta
    assert cp.restore("cp1", tmp_path / "store", None, apply=True) == 1
    out = capsys.readouterr().out
    assert "REVERTED alpha" in out and "reset --hard" in out      # how to undo the part that moved
    assert "FAILED   beta" in out
    assert (repos["alpha"] / "f.txt").read_text(encoding="utf-8") == "alpha v1\n"
    assert (repos["beta"] / "f.txt").read_text(encoding="utf-8") == "beta v2\n"


def test_restore_of_an_unknown_label_says_so(tmp_path):
    with pytest.raises(SystemExit):
        cp.restore("nope", tmp_path / "store", None, apply=True)
