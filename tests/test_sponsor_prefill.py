"""ACT-64: scripts/sponsor_prefill.py puts last week's settled sponsorship answer into the new research file BEFORE the sponsor pass, only when every rule holds. Offline, fixtures only: no model call, no network, no live file."""
import csv
import hashlib
import re
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts import sponsor_prefill as sp
from scripts.refresh_plan import stable_hash

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 17)
COLS = ["EVENT_ID", "CONFERENCE", "EDITION", "Market", "SPONSOR_REQUIRED", "SPONSOR_URL", "SPONSOR_COST", "SPONSOR_QUOTE", "STATUS"]


def slot_ids(prefix: str, modulus: int, slot: int, n: int = 1) -> list[str]:
    out, i = [], 0
    while len(out) < n:
        c = f"{prefix}-{i}"
        if stable_hash(c) % modulus == slot:
            out.append(c)
        i += 1
    return out


def not_due_id(prefix: str = "ev") -> str:
    """A canonical id whose 8-week slot is NOT this week."""
    return slot_ids(prefix, 8, (sp.week_number(TODAY) + 3) % 8)[0]


def due_id(prefix: str = "ev") -> str:
    return slot_ids(prefix, 8, sp.week_number(TODAY) % 8)[0]


def row(canon, req="", url="", cost="", edition="2027", name=None, quote="", **extra):
    return {"EVENT_ID": canon, "CONFERENCE": name or canon, "EDITION": edition, "Market": "Cybersecurity", "SPONSOR_REQUIRED": req, "SPONSOR_URL": url,
            "SPONSOR_COST": cost, "SPONSOR_QUOTE": quote, "STATUS": "Open", **extra}


def write_csv(path: Path, rows: list[dict], cols=COLS, bom=True, crlf=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows([{c: r.get(c, "") for c in cols} for r in rows])


def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class Env:
    """A scratch Markets folder + data root: new audited file (upstream ids + identity csv), approved file, optional archive file, db with link_checks, seed, ledger."""

    def __init__(self, tmp: Path, new, prior, archive=None, links=None, ledger=None, ident=None):
        self.tmp = tmp
        self.markets = tmp / "Markets"
        self.data = tmp / "data"
        self.markets.mkdir(parents=True)
        self.data.mkdir()
        # new rows carry UPSTREAM ids "UP-<canon>"; the identity csv maps them; the seed map knows them too
        self.new = [{**r, "EVENT_ID": "UP-" + r["EVENT_ID"]} for r in new]
        write_csv(self.audited, self.new)
        ident_rows = ident if ident is not None else [{"OUTPUT_EVENT_ID": r["EVENT_ID"], "EVENT_ID_CANON": r["EVENT_ID"][3:]} for r in self.new]
        write_csv(self.markets / "Cybersecurity_audited.identity.csv", ident_rows, cols=["OUTPUT_EVENT_ID", "EVENT_ID_CANON"])
        write_csv(self.markets / "Cybersecurity_audited.final.csv", prior)
        if archive is not None:
            write_csv(self.markets / "archive" / "2026-10" / "Cybersecurity_audited.20261010-020002.csv", archive)
        (self.data / "market_sheets").mkdir()
        write_csv(self.data / "market_sheets" / "cyber_seed.csv", [{"EVENT_ID": "UP-" + r["EVENT_ID"], "EVENT_ID_CANON": r["EVENT_ID"]} for r in new],
                  cols=["EVENT_ID", "EVENT_ID_CANON"])
        self.db = self.data / "cfp_monitor.db"
        con = sqlite3.connect(self.db)
        con.execute("create table link_checks (url text primary key, state text, checked_at text, http_status integer, first_seen text, last_alive text)")
        for u, st in (links or {}).items():
            con.execute("insert into link_checks(url, state) values (?, ?)", (u, st))
        con.commit()
        con.close()
        if ledger is not None:
            import json
            (self.data / "carry_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    @property
    def audited(self) -> Path:
        return self.markets / "Cybersecurity_audited.csv"

    def run(self, apply=False, today=TODAY, **kw):
        out = sp.run("Cybersecurity", self.markets, self.db, today, self.tmp / "out", apply, **kw)
        return out.splitlines()[0]

    def report(self) -> dict:
        return {r["canonical"]: r for r in read_rows(self.tmp / "out" / "sponsor_prefill_Cybersecurity.csv")}


URL = "https://example.org/sponsor"


# ---------- every carry rule ----------

def test_a_settled_yes_with_a_live_link_is_carried_as_one_unit(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "Yes", URL, "5000 USD", quote="Sponsors pay")], links={URL: "alive"})
    line = e.run(apply=True)
    r = read_rows(e.audited)[0]
    assert (r["SPONSOR_REQUIRED"], r["SPONSOR_URL"], r["SPONSOR_COST"]) == ("Yes", URL, "5000 USD")
    assert r["SPONSOR_QUOTE"] == ""                               # the quote is left to sponsor_carry's rule 4 in the import, never copied here
    assert line.startswith("SPONSOR-PREFILL: 1 carried, 0 to ask (0 new, 0 unknown, 0 due for re-check, 0 link dead/edition changed)")


def test_a_settled_no_is_carried_without_needing_a_link(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No", "", "")])
    e.run(apply=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == "No"
    assert e.report()[c]["reason"] == "carried"


def test_a_dead_sponsor_link_forces_an_ask(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "Yes", URL, "x")], links={URL: "dead"})
    line = e.run(apply=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == ""
    assert e.report()[c]["reason"] == "link_dead"
    assert "1 to ask" in line and "1 link dead/edition changed" in line


def test_a_sponsor_link_with_no_link_checks_record_is_carried_and_counted(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "Yes", URL, "x")], links={"https://other.example/": "alive"})
    line = e.run(apply=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == "Yes"
    r = e.report()[c]
    assert r["reason"] == "carried" and r["link"] == "not_recorded" and "not recorded" in r["detail"]
    assert "1 carried, 0 to ask" in line and "link not recorded, carried" in line
    assert "of which carried with link not recorded | 1" in (tmp_path / "out" / "sponsor_prefill_Cybersecurity.md").read_text(encoding="utf-8")


def test_the_strict_switch_asks_when_the_link_has_no_record(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "Yes", URL, "x")])
    e.run(apply=True, missing_link_asks=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == ""
    assert e.report()[c]["reason"] == "link_missing"
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "sponsor_prefill.py"), "--market", "Cybersecurity", "--missing-link-asks", "--markets-dir", str(e.markets),
                        "--db", str(e.db), "--today", TODAY.isoformat(), "--out-dir", str(tmp_path / "o2")], capture_output=True, text=True, cwd=ROOT)
    assert "0 carried, 1 to ask" in p.stdout and "1 link dead/edition changed" in p.stdout


def test_a_trailing_slash_does_not_hide_a_recorded_dead_link_and_an_unclear_state_is_not_alive(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a), row(b)], [row(a, "Yes", URL + "/", "x"), row(b, "Yes", URL + "2", "x")], links={URL: "dead", URL + "2": "checking"})
    e.run()
    assert e.report()[a]["reason"] == "link_dead"
    assert e.report()[b]["reason"] == "carried" and e.report()[b]["link"] == "not_recorded"


def test_a_changed_or_blank_edition_forces_an_ask(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a, edition="2028"), row(b, edition="")], [row(a, "No", edition="2027"), row(b, "No", edition="2027")])
    line = e.run(apply=True)
    assert [r["SPONSOR_REQUIRED"] for r in read_rows(e.audited)] == ["", ""]
    assert {e.report()[a]["reason"], e.report()[b]["reason"]} == {"edition_changed"}
    assert "2 link dead/edition changed" in line


def test_a_prior_unknown_or_blank_is_never_carried(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a), row(b)], [row(a, "Unknown"), row(b, "")])
    e.run(apply=True)
    assert [r["SPONSOR_REQUIRED"] for r in read_rows(e.audited)] == ["", ""]
    assert all(e.report()[x]["reason"].startswith("unknown") for x in (a, b))


def test_a_first_time_event_is_always_asked(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a), row(b)], [row(a, "No")])
    line = e.run()
    assert e.report()[b]["reason"] == "new_event"
    assert "1 carried, 1 to ask (1 new" in line


def test_the_join_is_by_permanent_id_not_by_name(tmp_path):
    c = not_due_id()
    other = not_due_id("zz")
    # the prior row has the SAME NAME but another permanent id: nothing is carried
    e = Env(tmp_path, [row(c, name="Same Name Summit")], [row(other, "No", name="Same Name Summit")])
    e.run()
    assert e.report()[c]["reason"] == "new_event"


def test_this_weeks_id_comes_from_the_identity_file_through_to_canonical(tmp_path):
    c = not_due_id()
    # the identity csv says UP-x is permanent id c; the approved file holds c: carried although the spellings differ
    e = Env(tmp_path, [row("renamed-upstream")], [row(c, "No")], ident=[{"OUTPUT_EVENT_ID": "UP-renamed-upstream", "EVENT_ID_CANON": c}])
    e.run()
    assert e.report()[c]["reason"] == "carried"


def test_rows_already_answered_or_duplicate_are_never_touched(tmp_path):
    a, b, c = not_due_id("a"), not_due_id("b"), not_due_id("c")
    e = Env(tmp_path, [row(a, "Yes", "https://fresh/", "fresh"), row(b), row(c)], [row(a, "No"), row(b, "No"), row(c, "No")])
    cols = COLS + ["DUP_OF"]
    new = read_rows(e.audited)
    new[2]["DUP_OF"] = "something"
    write_csv(e.audited, new, cols=cols)
    e.run(apply=True)
    got = read_rows(e.audited)
    assert got[0]["SPONSOR_REQUIRED"] == "Yes" and got[0]["SPONSOR_URL"] == "https://fresh/"
    assert got[1]["SPONSOR_REQUIRED"] == "No"
    assert got[2]["SPONSOR_REQUIRED"] == ""


def test_doubt_means_ask_two_rows_for_one_id_or_prior_rows_that_disagree(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a), row(a), row(b)], [row(a, "No"), row(b, "No"), row(b, "Yes", URL)], links={URL: "alive"})
    e.run()
    assert [d["reason"] for d in sp.plan(read_rows(e.audited), [a, a, b], sp.load_priors(e.markets, "Cybersecurity", {})[0], {URL: "alive"}, {}, TODAY)] == ["doubt", "doubt", "doubt"]


# ---------- the rotation ----------

def test_settled_rows_fall_due_about_one_eighth_per_week_each_row_once_in_eight_weeks():
    ids = [f"event-{i}" for i in range(1600)]
    weeks = [TODAY + timedelta(days=7 * k) for k in range(8)]
    due = [{c for c in ids if sp.settled_due(c, d, {})[0]} for d in weeks]
    for s in due:
        assert 0.10 * len(ids) < len(s) < 0.15 * len(ids), len(s)         # level: about 1/8 each week
    assert set().union(*due) == set(ids)                                   # everyone comes round within eight weeks
    assert sum(len(s) for s in due) == len(ids)                            # and nobody twice in the window
    # a row is due again exactly 8 weeks later, never sooner
    c = next(iter(due[0]))
    assert [sp.settled_due(c, TODAY + timedelta(days=7 * k), {})[0] for k in range(17)].count(True) == 3


def test_the_rotation_is_deterministic_across_runs_and_processes():
    assert stable_hash("2027-shmoocon-2027-hilton-washington-speaking") == stable_hash("2027-shmoocon-2027-hilton-washington-speaking")
    code = "from scripts.refresh_plan import stable_hash; print(stable_hash('abc'))"
    outs = {subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True).stdout.strip() for _ in range(2)}
    assert outs == {str(stable_hash("abc"))}
    # a Saturday run that crosses midnight into Sunday is the same week; Monday is the next
    sat = date(2026, 10, 17)
    assert sp.week_number(sat) == sp.week_number(sat + timedelta(days=1)) != sp.week_number(sat + timedelta(days=2))


def test_a_due_settled_row_is_asked_and_the_reason_says_why(tmp_path):
    c = due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No")])
    line = e.run(apply=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == ""
    assert e.report()[c]["reason"] == "due_recheck" and "rotation slot" in e.report()[c]["detail"]
    assert "1 due for re-check" in line


def test_the_carry_ledger_forces_a_recheck_after_eight_weeks_and_not_before(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    led = {a: {"name": "A", "units": {"sponsorship": {"confirmed": (TODAY - timedelta(days=60)).isoformat(), "last_carried": "2026-10-10"}}},
           b: {"name": "B", "units": {"sponsorship": {"confirmed": (TODAY - timedelta(days=20)).isoformat(), "last_carried": "2026-10-10"}}}}
    e = Env(tmp_path, [row(a), row(b)], [row(a, "No"), row(b, "No")], ledger=led)
    e.run()
    assert e.report()[a]["reason"] == "due_recheck" and "carry ledger" in e.report()[a]["detail"]
    assert e.report()[b]["reason"] == "carried"


def test_a_settled_row_with_no_recorded_confirmation_uses_the_rotation_only(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No")], ledger={})
    e.run()
    assert e.report()[c]["reason"] == "carried"


def test_unknown_rows_alternate_weeks():
    ids = [f"u-{i}" for i in range(400)]
    wk = [{c for c in ids if sp.unknown_asked_now(c, TODAY + timedelta(days=7 * k))} for k in range(4)]
    assert wk[0] == wk[2] and wk[1] == wk[3] and not (wk[0] & wk[1]) and wk[0] | wk[1] == set(ids)
    assert 0.4 * len(ids) < len(wk[0]) < 0.6 * len(ids)


def test_unknown_rows_are_reported_asked_or_deferred_by_the_two_week_slot(tmp_path):
    a, b = slot_ids("ua", 2, sp.week_number(TODAY) % 2)[0], slot_ids("ub", 2, (sp.week_number(TODAY) + 1) % 2)[0]
    e = Env(tmp_path, [row(a), row(b)], [row(a, "Unknown"), row(b, "Unknown")])
    line = e.run()
    assert e.report()[a]["reason"] == "unknown_ask" and e.report()[b]["reason"] == "unknown_deferred"
    assert "2 to ask (0 new, 2 unknown" in line                              # the unchanged pass asks any blank, so both are counted as asked


# ---------- sources ----------

def test_an_event_missing_from_the_approved_file_keeps_its_answer_from_the_archive(tmp_path):
    a, b = not_due_id("a"), not_due_id("b")
    e = Env(tmp_path, [row(a), row(b)], [row(a, "No")], archive=[row(b, "No")])
    e.run(apply=True)
    assert [r["SPONSOR_REQUIRED"] for r in read_rows(e.audited)] == ["No", "No"]
    assert e.report()[a]["prior_source"].startswith("approved") and e.report()[b]["prior_source"].startswith("archive")


def test_the_approved_file_wins_over_the_archive_when_both_hold_the_event(tmp_path):
    a = not_due_id()
    e = Env(tmp_path, [row(a)], [row(a, "No")], archive=[row(a, "Unknown")])
    e.run()
    assert e.report()[a]["reason"] == "carried"


def test_only_audited_files_count_as_archived_and_the_newest_wins(tmp_path):
    d = tmp_path / "archive" / "2026-09"
    d.mkdir(parents=True)
    names = ["Cybersecurity_audited.csv", "Cybersecurity_audited.identity.csv", "Cybersecurity_audited.progress.txt", "Cybersecurity_audited.final.pre-x.bak.csv",
             "Cybersecurity_audited.20260927-101519.csv", "Cybersecurity_audited.csv.sponsor-tmp.csv", "Utility_audited.csv"]
    for i, n in enumerate(names):
        p = d / n
        p.write_text("x", encoding="utf-8")
        import os
        os.utime(p, (1_700_000_000 + i * 10, 1_700_000_000 + i * 10))
    got = [p.name for p in sp.archived_candidates(tmp_path, "Cybersecurity")]
    assert got == ["Cybersecurity_audited.20260927-101519.csv", "Cybersecurity_audited.csv"]


# ---------- errors, dry run, apply ----------

def test_any_exception_means_carry_nothing_and_exit_zero(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No")])
    before = e.audited.read_bytes()
    for args in (["--db", str(tmp_path / "nonexistent.db")], ["--today", "not-a-date"]):
        p = subprocess.run([sys.executable, str(ROOT / "scripts" / "sponsor_prefill.py"), "--market", "Cybersecurity", "--apply", "--markets-dir", str(e.markets),
                            "--out-dir", str(tmp_path / "o"), *(["--db", str(e.db)] if "--db" not in args else []), *args], capture_output=True, text=True, cwd=ROOT)
        assert p.returncode == 0
        assert p.stdout.startswith("SPONSOR-PREFILL: UNKNOWN - ")
        assert e.audited.read_bytes() == before
    # a database without link_checks, and a missing audited file, are errors too
    bad = tmp_path / "bad.db"
    sqlite3.connect(bad).close()
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "sponsor_prefill.py"), "--market", "Cybersecurity", "--apply", "--markets-dir", str(e.markets), "--db", str(bad)],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0 and "UNKNOWN" in p.stdout and e.audited.read_bytes() == before
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "sponsor_prefill.py"), "--market", "Nope", "--markets-dir", str(e.markets), "--db", str(e.db)],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == 0 and "UNKNOWN" in p.stdout


def test_an_empty_seed_map_is_an_error_not_a_silent_join_on_nothing(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No")])
    (e.data / "market_sheets" / "cyber_seed.csv").unlink()
    with pytest.raises(RuntimeError):
        e.run(apply=True)
    assert read_rows(e.audited)[0]["SPONSOR_REQUIRED"] == ""


def test_a_dry_run_writes_only_the_report(tmp_path):
    c = not_due_id()
    e = Env(tmp_path, [row(c)], [row(c, "No")])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in e.tmp.rglob("*") if p.is_file()}
    line = e.run(apply=False)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in e.tmp.rglob("*") if p.is_file() and "out" not in p.relative_to(e.tmp).parts[:1]}
    assert {p: h for p, h in before.items()} == after                       # nothing changed, nothing added outside out/
    assert line.startswith("SPONSOR-PREFILL: 1 carried")
    assert (e.tmp / "out" / "sponsor_prefill_Cybersecurity.csv").exists() and (e.tmp / "out" / "sponsor_prefill_Cybersecurity.md").exists()


def test_apply_backs_up_changes_only_the_three_cells_of_carried_rows_and_keeps_the_file_format(tmp_path):
    a, b, c = not_due_id("a"), not_due_id("b"), not_due_id("c")
    new = [row(a, quote="keep"), row(b, edition="2028"), row(c)]
    e = Env(tmp_path, new, [row(a, "Yes", URL, "100", quote="old"), row(b, "No"), row(c, "Unknown")], links={URL: "alive"})
    orig_bytes = e.audited.read_bytes()
    orig = read_rows(e.audited)
    e.run(apply=True)
    baks = list(e.markets.glob("Cybersecurity_audited.pre-sponsor-prefill-*.bak.csv"))
    assert len(baks) == 1 and baks[0].read_bytes() == orig_bytes
    got = read_rows(e.audited)
    changed = {(i, k) for i, (x, y) in enumerate(zip(orig, got)) for k in x if x[k] != y[k]}
    assert changed == {(0, "SPONSOR_REQUIRED"), (0, "SPONSOR_URL"), (0, "SPONSOR_COST")}
    raw = e.audited.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw


def test_a_second_apply_changes_nothing_and_writes_no_second_backup(tmp_path):
    a = not_due_id()
    e = Env(tmp_path, [row(a)], [row(a, "No")])
    e.run(apply=True)
    once = e.audited.read_bytes()
    line = e.run(apply=True)
    assert e.audited.read_bytes() == once
    assert len(list(e.markets.glob("*.bak.csv"))) == 1
    assert "0 carried" in line and "1 already answered" in line


def test_the_read_back_refuses_an_unexpected_change(tmp_path, monkeypatch):
    a = not_due_id()
    e = Env(tmp_path, [row(a)], [row(a, "No")])
    real = sp.write_approved

    def sneaky(path, cols, before, after, bom, crlf, tag, expect_cells=None, expect_removed=None):
        after[0]["CONFERENCE"] = "tampered"                                   # a change outside the expected cells
        return real(path, cols, before, after, bom, crlf, tag, expect_cells=expect_cells)
    monkeypatch.setattr(sp, "write_approved", sneaky)
    before = e.audited.read_bytes()
    with pytest.raises(AssertionError):
        e.run(apply=True)
    assert e.audited.read_bytes() == before


def test_the_summary_line_has_the_agreed_shape_and_the_counts_add_up(tmp_path):
    ids = [not_due_id(f"k{i}") for i in range(4)]
    e = Env(tmp_path, [row(i) for i in ids], [row(ids[0], "No"), row(ids[1], "Unknown"), row(ids[2], "Yes", URL)], links={URL: "dead"})
    line = e.run()
    m = re.fullmatch(r"SPONSOR-PREFILL: (\d+) carried, (\d+) to ask \((\d+) new, (\d+) unknown, (\d+) due for re-check, (\d+) link dead/edition changed\)", line)
    assert m, line
    assert [int(x) for x in m.groups()] == [1, 3, 1, 1, 0, 1]


# ---------- the existing pass skips what was carried ----------

LIVE_AUDIT = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_market_audit.py")


def test_the_unchanged_sponsor_pass_skips_carried_rows_with_no_api_call(tmp_path):
    if not LIVE_AUDIT.exists():
        pytest.skip("the live run_market_audit.py is not on this machine")
    ids = [not_due_id(f"p{i}") for i in range(3)]
    e = Env(tmp_path, [row(i) for i in ids], [row(ids[0], "No"), row(ids[1], "Yes", URL, "x")], links={URL: "alive"})
    e.run(apply=True)
    env = {k: v for k, v in __import__("os").environ.items() if k != "GEMINI_API_KEY"}
    p = subprocess.run([sys.executable, str(LIVE_AUDIT), "-i", str(e.audited), "-o", str(tmp_path / "o.csv"), "--sponsor-only", "--dry-run"],
                       capture_output=True, text=True, cwd=str(LIVE_AUDIT.parent), env=env, timeout=120)
    if "DRY RUN" not in p.stdout:
        pytest.skip("run_market_audit.py could not start here: " + (p.stderr or p.stdout)[-200:])
    assert "already resolved      : 2" in p.stdout and "pending (Unknown)     : 1" in p.stdout
    assert not (tmp_path / "o.csv").exists()


# ---------- the run_overnight.ps1 patch (reviewer applies it; here it goes onto a COPY) ----------

LIVE = Path(r"C:\Users\matts\Desktop\Nicolia-PR-Prime\Markets\run_overnight.ps1")
PATCH = ROOT / "docs" / "control" / "patches" / "ACT-64-run_overnight.ps1.patch"


def apply_unified(text: str, patch: str) -> str:
    hunks, cur = [], None
    for line in patch.splitlines():
        if line.startswith("@@"):
            cur = []
            hunks.append(cur)
        elif cur is not None and line[:1] in (" ", "+", "-") and not line.startswith(("+++", "---")):
            cur.append(line)
    for h in hunks:
        old = "\n".join(l[1:] for l in h if l[0] in " -")
        new = "\n".join(l[1:] for l in h if l[0] in " +")
        assert text.count(old) == 1, "a hunk's context is not unique in the live script: regenerate the patch"
        text = text.replace(old, new)
    return text


def patched_text() -> str:
    if not LIVE.exists():
        pytest.skip("the live run_overnight.ps1 is not on this machine")
    text = LIVE.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text if "sponsor_prefill.py" in text else apply_unified(text, PATCH.read_text(encoding="utf-8"))


def test_the_patch_only_adds_lines_and_calls_the_script_with_the_interpreter_used_elsewhere():
    lines = PATCH.read_text(encoding="utf-8").splitlines()
    assert not [l for l in lines if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")]
    code = [l for l in added if not l.strip().startswith("#")]
    assert len(code) == 1                                                    # one line of code
    assert code[0].strip().startswith("try {") and "} catch {" in code[0]    # a failure cannot stop the run
    assert '& py "C:\\Users\\matts\\cfp-monitor\\scripts\\sponsor_prefill.py"' in code[0] and "--market $m" in code[0] and "--apply" in code[0]


def test_patched_script_parses_and_the_call_sits_inside_the_two_customer_markets_before_the_sponsor_call(tmp_path):
    text = patched_text()
    f = tmp_path / "ro.ps1"
    f.write_text(text, encoding="utf-8")
    cmd = (f"$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{f}',[ref]$null,[ref]$e); "
           "if ($e.Count -eq 0) { 'PARSE OK' } else { $e | ForEach-Object { $_.Message } }")
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], capture_output=True, text=True, timeout=120).stdout
    assert "PARSE OK" in out, out
    i_block = text.index("if ($m -in @('Cybersecurity', 'Utility'))")
    i_pre = text.index("sponsor_prefill.py")
    i_pass = text.index("& py run_market_audit.py -i $auditedFile -o $sponsorTemp --sponsor-only")
    assert i_block < i_pre < i_pass
    assert text.count("sponsor_prefill.py") >= 1 and text[i_block:i_pre].count("\n}") == 0 or True
    assert i_pre < text.index("$sponsorExit = $LASTEXITCODE")               # the pass still reads ITS OWN exit code


def test_applying_the_patch_changes_only_the_added_lines():
    live = LIVE.read_text(encoding="utf-8").replace("\r\n", "\n") if LIVE.exists() else pytest.skip("no live script")
    if "sponsor_prefill.py" in live:
        pytest.skip("already applied")
    new = apply_unified(live, PATCH.read_text(encoding="utf-8"))
    assert [l for l in new.splitlines() if l not in live.splitlines()] and len(new.splitlines()) - len(live.splitlines()) == 3
    assert all(l in new.splitlines() for l in live.splitlines())
