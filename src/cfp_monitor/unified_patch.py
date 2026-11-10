"""Apply a unified diff (one file, as written in docs/control/patches/) to a script's TEXT, in memory. Pure; touches no file.

Used to rehearse a Markets patch before the operator applies it (scripts/customer_row_context.py --rehearse) and by its tests. Every hunk's
old text must occur exactly once in the target, or it raises: a patch whose context no longer matches the live script must be regenerated,
never applied fuzzily. Line endings are compared as LF; the caller decides how to write the result."""
from __future__ import annotations


class PatchDoesNotApply(ValueError):
    pass


def apply_unified(text: str, patch: str) -> str:
    text = text.replace("\r\n", "\n")
    hunks: list[list[str]] = []
    cur: list[str] | None = None
    for line in patch.replace("\r\n", "\n").splitlines():
        if line.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif cur is not None and line[:1] in (" ", "+", "-") and not line.startswith(("+++", "---")):
            cur.append(line)
    if not hunks:
        raise PatchDoesNotApply("the patch has no hunks")
    for h in hunks:
        old = "\n".join(ln[1:] for ln in h if ln[0] in " -")
        new = "\n".join(ln[1:] for ln in h if ln[0] in " +")
        n = text.count(old)
        if n != 1:
            raise PatchDoesNotApply(f"a hunk's context occurs {n} times in the target, not once: regenerate the patch")
        text = text.replace(old, new)
    return text
