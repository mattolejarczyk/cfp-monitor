"""scripts/check_delivery_ids.py: an id upstream sends must be traced to where we hold it."""
from scripts.check_delivery_ids import locate


def test_unknown_known_and_not_queued():
    src = {"database": {"2026-a-houston"}, "this week's research": set(), "approved file": {"2026-a-houston"}, "input list": set()}
    res = {r["id"]: r for r in locate(["2026-a-houston-speaking", "2026-a-houston", "ghost"], src, {})}
    assert res["2026-a-houston-speaking"]["unknown"]                      # their spelling is not ours: UNKNOWN, not guessed
    assert res["2026-a-houston"]["not_queued"] and not res["2026-a-houston"]["unknown"]
    assert res["ghost"]["unknown"]


def test_translation_through_the_seed_map():
    src = {"database": {"2026-a-houston"}, "input list": {"2026-a-houston"}}
    r = locate(["up-1"], src, {"up-1": "2026-a-houston"})[0]
    assert not r["unknown"] and not r["not_queued"] and r["canonical"] == "2026-a-houston"


# ---- ACT-16: the note 27 table by command; sparse patches refused; wired into the gate -----------------
import csv
import sqlite3

from scripts import check_delivery_ids as cdi

HELD = {
    "2026-argus-biofuels-europe-conference-exhibition-london": ("Argus Biofuels Europe Conference & Exhibition 2026", "London", "Open"),
    "2027-ces-las-vegas": ("CES 2027", "Las Vegas", "Open"),
    "2026-owasp-global-appsec-usa-san-francisco": ("OWASP Global AppSec USA 2026", "San Francisco", "Closed"),
    "2027-showstoppers-ces-las-vegas-exhibiting": ("ShowStoppers @ CES 2027", "Las Vegas", "Open"),
}
THEIRS = ["2026-argus-biofuels-europe-conference-london-speaking", "2027-ces-las-vegas-speaking",
          "2026-owasp-global-appsec-usa-washington-speaking", "2027-showstoppers-ces-las-vegas-speaking",
          "2030-nothing-like-it-nowhere-speaking", "2027-ces-las-vegas"]


def _db(tmp_path):
    p = tmp_path / "t.db"
    con = sqlite3.connect(p)
    for t in ("grounding_facts", "award_grounding_facts"):
        con.execute(f"create table {t} (event_id, name, city, status)")
    for k, (n, c, s) in HELD.items():
        con.execute("insert into grounding_facts values (?,?,?,?)", (k, n, c, s))
    con.commit()
    con.close()
    return str(p)


def _csv(tmp_path, ids, ncols):
    p = tmp_path / "patch.csv"
    cols = ["EVENT_ID", "Market"] + [f"C{i}" for i in range(ncols - 2)]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i in ids:
            w.writerow([i, "Cybersecurity"] + [""] * (ncols - 2))
    return str(p)


def test_suggest_reproduces_the_note_27_table():
    held = {k: {"name": v[0], "city": v[1], "status": v[2], "table": "grounding_facts"} for k, v in HELD.items()}
    assert cdi.suggest(THEIRS[0], held)["id"] == "2026-argus-biofuels-europe-conference-exhibition-london"
    assert cdi.suggest(THEIRS[1], held)["id"] == "2027-ces-las-vegas"
    s = cdi.suggest(THEIRS[2], held)
    assert s["id"] == "2026-owasp-global-appsec-usa-san-francisco" and s["city"] == "San Francisco"   # they say Washington
    assert cdi.suggest(THEIRS[3], held)["id"].endswith("showstoppers-ces-las-vegas-exhibiting")       # role differs: shown, not decided
    assert cdi.suggest(THEIRS[4], held) is None                                                       # nothing resembles it
    assert cdi.suggest("2025-ces-las-vegas-speaking", held) is None                                   # other year is not the same edition


def test_analyse_and_table(tmp_path):
    db = _db(tmp_path)
    rows = [{"EVENT_ID": i} for i in THEIRS]
    out = cdi.analyse(rows, "Cybersecurity", db, str(tmp_path))
    unk = [r["id"] for r in out["results"] if r["unknown"]]
    assert "2027-ces-las-vegas" not in unk and len(unk) == 5
    table = cdi.format_table(out["results"])
    assert "-> 2026-owasp-global-appsec-usa-san-francisco   (San Francisco" in table
    assert "no id we hold resembles it" in table


def test_sparse_patch_with_unknown_id_is_refused_by_default(tmp_path, capsys, monkeypatch):
    db = _db(tmp_path)
    sparse = _csv(tmp_path, THEIRS[:3], 8)
    monkeypatch.setattr("sys.argv", ["x", sparse, "--db", db, "--markets-dir", str(tmp_path)])
    assert cdi.main() == 1
    assert "REFUSED" in capsys.readouterr().out
    full = _csv(tmp_path, THEIRS[:3], 45)
    monkeypatch.setattr("sys.argv", ["x", full, "--db", db, "--markets-dir", str(tmp_path)])
    assert cdi.main() == 0                      # a full delivery may carry new events: report only


def test_gate_check_ids_fails_sparse_and_notes_full(tmp_path):
    from scripts.accept_delivery import Gate
    db = _db(tmp_path)
    for ncols, expect_pass in ((8, False), (45, True)):
        g = Gate(_csv(tmp_path, THEIRS[:3], ncols), network=False)
        g.check_structure()
        g.check_ids(db, "Cybersecurity", str(tmp_path))
        res = [r for r in g.results if r[0] == "9"][0]
        assert res[2] is expect_pass
        assert any(n[0] == "9" for n in g.notes)
