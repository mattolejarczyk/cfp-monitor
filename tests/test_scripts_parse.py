"""Every script must at least parse.

Trivial, and it exists because a syntax error was committed AND PUSHED on 2026-08-11. The full
suite passed the whole time: no test imports `run_full_cycle.py`, so nothing ever compiled it.
The tests were green and the entry point was broken.

A test suite only covers what it imports. These scripts are the operator's entry points - the
things run at 2am by someone who will not debug them - so the cheapest possible check that
they are loadable belongs here.

Parsing is not importing and importing is not working. This catches the dumbest failure only,
which is the one that got through.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY_FILES = sorted(
    p for p in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "src").rglob("*.py"))
    if p.name != "__init__.py"
)


def test_there_are_scripts_to_check():
    """Guards the guard: a glob that matches nothing passes every parametrised test below."""
    assert len(PY_FILES) > 15, f"only found {len(PY_FILES)} files - has the layout moved?"


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_parses(path: Path):
    src = path.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(path))
    except SyntaxError as e:
        pytest.fail(f"{path.relative_to(ROOT)}:{e.lineno}  {e.msg}\n    {(e.text or '').rstrip()}")
