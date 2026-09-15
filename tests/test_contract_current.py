"""The contract file in this repo must name every amendment sitting beside it.

Until 2026-09-15 `pipeline-contract.md` held Version 1.1 from 2026-08-01 while the contract in
force was v2.0.1 plus five amendments - and the `cfp-protocol` skill sends every new session
there to read it as "the why". A session following the documented procedure got superseded
rules, and nothing failed.

Adopting an amendment is a conversation with upstream; remembering to update a header six weeks
later is not something anyone does reliably. So the build checks it instead.
"""
from __future__ import annotations

import re
from pathlib import Path

OPS = Path(__file__).resolve().parents[1] / "docs" / "operations"
CONTRACT = OPS / "pipeline-contract.md"


def amendment_files() -> dict[str, Path]:
    """Every live amendment beside the contract, keyed by its version: {"2.5": Path(...)}."""
    out = {}
    for p in OPS.glob("Contract_v2.*.md"):
        m = re.match(r"Contract_v(\d+\.\d+)_", p.name)
        if m:
            out[m.group(1)] = p
    return out


def test_the_contract_file_is_not_a_superseded_version():
    head = CONTRACT.read_text(encoding="utf-8")[:2000]
    assert "STATUS:        CURRENT" in head, "the contract must declare its own status"
    assert not re.search(r"^\*\*Version 1\.\d+\*\*", head, re.M), (
        "this file is a superseded version of the contract - the in-force text is v2.0.1 plus "
        "its amendments")


def test_every_amendment_present_is_named_in_the_header():
    """The failure this exists for: an amendment lands in the folder and the header never
    learns about it, so the file reads as current while being incomplete."""
    head = CONTRACT.read_text(encoding="utf-8")[:6000]
    missing = [v for v in sorted(amendment_files()) if f"v{v}" not in head]
    assert not missing, (
        f"amendment(s) {missing} sit in docs/operations but are not named in the contract "
        f"header. Add the row to the table and update the IN FORCE line in the same change.")


def test_every_amendment_named_in_the_header_actually_exists():
    """The inversion. A header promising a document that is not there sends a reader hunting
    for rules they cannot read, which is worse than an honest gap."""
    head = CONTRACT.read_text(encoding="utf-8")[:6000]
    named = set(re.findall(r"\bv(2\.\d+)\b", head)) - {"2.0"}
    present = set(amendment_files())
    assert named <= present, (
        f"the header names {sorted(named - present)} but no such file is in docs/operations")


def test_each_amendment_is_linked_so_a_reader_can_reach_it():
    body = CONTRACT.read_text(encoding="utf-8")
    for version, path in sorted(amendment_files().items()):
        assert f"]({path.name})" in body, (
            f"v{version} is not linked by filename; a reader following the skill cannot reach it")


def test_the_amendments_are_readable_and_declare_a_status():
    """Every document in this trail carries a STATUS line - the convention that exists because
    on 2026-09-05 we had to ask upstream whether their own agreed amendment was agreed."""
    for version, path in sorted(amendment_files().items()):
        head = path.read_text(encoding="utf-8")[:1200]
        assert "STATUS" in head, f"v{version} ({path.name}) declares no STATUS"
