"""ACT-67: scripts/customer_awards.py - coverage of the customers' AWARDS sheets against Awards_input.csv, and the gated automatic add. FIXTURES ONLY (tmp_path); nothing live is read or written."""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import customer_awards as ca          # noqa: E402

TODAY = "2026-10-12"
INPUT_COLS = ["CONFERENCE", "CONFERENCE URL", "LOCATION", "SUBMISSION DEADLINE", "PRIORITY", "STATUS", "SUBMISSION URL", "RESEARCH STATUS", "EDITION", "START DATE", "Market",
              "OPPORTUNITY_TYPE", "OPERATOR", "SOURCE_SHEET", "DUP_OF", "EVENT_ID_CANON", "REFRESH_SKIP"]
ARNICA_COLS = ["AWARD", "LOCATION", "EVENT DATE", "SUBMISSION DEADLINE", "PRIORITY", "STATUS", "SUBMISSION URL"]
UTILITY_COLS = ["AWARD", "LOCATION", "EVENT DATE", "SUBMISSION DEADLINE", "PRIORITY", "SUBMISSION STATUS", "SUBMISSION URL"]   # Utility Global names its status column differently


def write(path, cols, rows, bom=True, crlf=False):
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, quoting=csv.QUOTE_ALL, lineterminator="\r\n" if crlf else "\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in cols} for r in rows)


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def world(tmp_path, arnica=(), utility=(), inputs=(), ledger=()):
    sheets, md = tmp_path / "sheets", tmp_path / "markets"
    sheets.mkdir(), md.mkdir()
    write(sheets / "arnica-awards.csv", ARNICA_COLS, list(arnica) or [{"AWARD": "Placeholder Award", "SUBMISSION URL": "https://placeholder.example/x"}])
    write(sheets / "utility-awards.csv", UTILITY_COLS, list(utility) or [{"AWARD": "Placeholder Prize", "SUBMISSION URL": "https://placeholder2.example/x"}])
    base = [{"CONFERENCE": "Placeholder Award", "SUBMISSION URL": "https://placeholder.example/x", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-placeholder-award-nan-awards"},
            {"CONFERENCE": "Placeholder Prize", "SUBMISSION URL": "https://placeholder2.example/x", "Market": "Utility", "EVENT_ID_CANON": "2026-placeholder-prize-nan-awards"}]
    write(md / "Awards_input.csv", INPUT_COLS, base + list(inputs), crlf=True)
    led = tmp_path / "ledger.csv"
    write(led, ["event_name", "url", "client", "reason", "ruled_by", "ruled_on"], list(ledger))
    return sheets, md, led


def go(tmp_path, apply=False, cap=30, **kw):
    sheets, md, led = world(tmp_path, **kw)
    out = tmp_path / "out"
    lines, code = ca.run(TODAY, sheets, md, led, out, cap, apply)
    return lines, md, out, code


def test_name_key_ignores_case_ampersand_parentheses_years_and_a_year_cut_off_mid_way():
    assert ca.name_key("Grist 50 (2026)") == ca.name_key("grist 50 2026") == ca.name_key("GRIST 50") == "grist 50"
    assert ca.name_key("S&P Global Platts Global Energy Awards (2026 portal)") == ca.name_key("S and P Global Platts Global Energy Awards")
    assert ca.name_key("Sustainability Leaders Awards (Edie) 2") == ca.name_key("Sustainability Leaders Awards (edie) 2026")
    assert ca.name_key("Grist 50") != ca.name_key("Grist 5"), "only a cut-off YEAR is repaired, never another number"


def test_url_key_keeps_the_query_and_ignores_a_bare_website():
    assert ca.url_key("https://www.tmcnet.com/tmc/poty/default.aspx?AwardID=807") != ca.url_key("https://www.tmcnet.com/tmc/poty/default.aspx?AwardID=808")
    assert ca.url_key("HTTP://WWW.Example.org/awards/#top") == ca.url_key("https://example.org/awards") == "example.org/awards"
    assert ca.url_key("https://www.blackhat.com/") == "", "a bare website says nothing about which award it is"


def test_status_is_read_from_either_column_name():
    sheets, md, led = world(Path(__import__("tempfile").mkdtemp()), arnica=[{"AWARD": "A1", "STATUS": "Submitted"}], utility=[{"AWARD": "U1", "SUBMISSION STATUS": "Closed"}])
    assert ca.sheet_rows(sheets / "arnica-awards.csv", "arnica-awards")[0]["status"] == "Submitted"
    assert ca.sheet_rows(sheets / "utility-awards.csv", "utility-awards")[0]["status"] == "Closed"


def test_an_award_on_the_list_by_name_or_by_deep_url_is_in_the_queue_and_a_new_one_is_not(tmp_path):
    inp = [{"CONFERENCE": "Grist 50 2026", "SUBMISSION URL": "https://grist.org/fix/50", "Market": "Utility", "EVENT_ID_CANON": "2026-grist-50-nan-awards"},
           {"CONFERENCE": "Old Name Of Prize", "SUBMISSION URL": "https://prize.example/enter", "Market": "Utility", "EVENT_ID_CANON": "2026-old-nan-awards"}]
    util = [{"AWARD": "Grist 50", "SUBMISSION URL": "https://x.example/a"},                   # same name key
            {"AWARD": "Renamed Prize", "SUBMISSION URL": "https://www.prize.example/enter/"},   # same deep URL
            {"AWARD": "Brand New Prize", "SUBMISSION URL": "https://new.example/enter"}]
    lines, md, out, _ = go(tmp_path, utility=util, inputs=inp)
    assert lines[0].startswith("AWARDS COVERAGE: 3 of 4 customer awards are on the research input list; 1 are NOT")
    res = ca.check({"utility-awards": ca.sheet_rows(tmp_path / "sheets" / "utility-awards.csv", "utility-awards"),
                    "arnica-awards": ca.sheet_rows(tmp_path / "sheets" / "arnica-awards.csv", "arnica-awards")}, read(md / "Awards_input.csv"), [])
    how = {x["name"]: x["why"] for x in res["in_queue"]}
    assert how["Grist 50"] == "by name" and how["Renamed Prize"] == "by submission URL"
    assert [x["name"] for x in res["not_in_queue"]] == ["Brand New Prize"]


def test_two_awards_with_the_same_query_free_family_page_are_not_paired_by_url(tmp_path):
    inp = [{"CONFERENCE": "TMC Family Award", "SUBMISSION URL": "https://tmc.example/poty/default.aspx", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-tmc-nan-awards"}]
    arn = [{"AWARD": "TMC Family Award", "SUBMISSION URL": "https://tmc.example/poty/default.aspx"},
           {"AWARD": "Other TMC Award", "SUBMISSION URL": "https://tmc.example/poty/default.aspx"}]
    _, md, out, _ = go(tmp_path, arnica=arn, inputs=inp)
    assert [p["award"] for p in read(out / "awards_proposed_additions.csv")] == ["Other TMC Award"]


def test_a_dup_of_row_is_excluded_with_its_reason_and_listed_as_separately_listed_by_the_customer(tmp_path):
    inp = [{"CONFERENCE": "Cloud Awards Security", "SUBMISSION URL": "https://cloud.example/a", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-cloud-nan-awards"},
           {"CONFERENCE": "Cloud Security Awards - SaaS family", "SUBMISSION URL": "https://cloud.example/b", "Market": "Cybersecurity", "DUP_OF": "Cloud Awards Security"}]
    arn = [{"AWARD": "Cloud Security Awards - SaaS family", "PRIORITY": "Urgent", "SUBMISSION DEADLINE": "10/23/2026", "SUBMISSION URL": "https://cloud.example/b"}]
    lines, md, out, _ = go(tmp_path, arnica=arn, inputs=inp)
    assert "1 excluded with a reason" in lines[0] and "AWARDS COVERAGE NOT IN QUEUE" not in "\n".join(lines)
    text = (out / "awards_coverage.md").read_text(encoding="utf-8")
    assert "labelled DUP_OF 'Cloud Awards Security'" in text and "Urgent" in text and "10/23/2026" in text, "the customer's own priority and date are shown"
    assert read(out / "awards_proposed_additions.csv") == [], "a DUP_OF name is never re-added"


def test_the_ledger_only_excludes_for_its_own_sheet(tmp_path):
    led = [{"event_name": "Odd Summit", "url": "", "client": "utility", "reason": "conference ruling", "ruled_by": "op", "ruled_on": "2026-10-06"},            # the conference sheet's client name
           {"event_name": "Declined Award", "url": "", "client": "arnica-awards", "reason": "customer declined", "ruled_by": "op", "ruled_on": "2026-10-12"}]
    util = [{"AWARD": "Odd Summit", "SUBMISSION URL": "https://odd.example/a"}]
    arn = [{"AWARD": "Declined Award", "SUBMISSION URL": "https://dec.example/a"}]
    lines, md, out, _ = go(tmp_path, arnica=arn, utility=util, ledger=led)
    props = [p["award"] for p in read(out / "awards_proposed_additions.csv")]
    assert props == ["Odd Summit"], "the conference ledger does not rule on an awards row; the awards ledger entry does"


def test_an_award_listed_only_under_the_other_market_is_added_as_a_market_sibling_row(tmp_path):
    inp = [{"CONFERENCE": "Fast Co Innovators", "SUBMISSION URL": "https://fc.example/a", "Market": "Utility", "EVENT_ID_CANON": "2027-fc-nan-awards", "STATUS": "Submitted", "PRIORITY": "Low"}]
    arn = [{"AWARD": "Fast Co Innovators", "PRIORITY": "High", "SUBMISSION URL": "https://fc.example/a"}]
    lines, md, out, _ = go(tmp_path, arnica=arn, inputs=inp)
    assert "1 only under the other market" in lines[0] and "AWARDS COVERAGE WRONG MARKET: Fast Co Innovators" in lines
    assert any(l.startswith("AWARDS AUTOADD: mode=dry-run; 1 to add, 0 held") for l in lines), "no longer held: the customer's sheet is the source of truth"
    (tmp_path / "again").mkdir()
    lines, md, out, _ = go(tmp_path / "again", arnica=arn, inputs=inp, apply=True)
    rows = read(md / "Awards_input.csv")
    assert len(rows) == 4
    sib = rows[-1]
    assert (sib["CONFERENCE"], sib["Market"], sib["DUP_OF"], sib["EVENT_ID_CANON"]) == ("Fast Co Innovators", "Cybersecurity", "MARKET_SIBLING", "2027-fc-nan-awards")
    assert sib["STATUS"] == "" and sib["PRIORITY"] == "" and sib["SOURCE_SHEET"] == "Arnica:2", "the other customer's status and priority are not copied"
    assert rows[2]["Market"] == "Utility" and rows[2]["DUP_OF"] == "" and rows[2]["STATUS"] == "Submitted", "the primary row is untouched"
    sheets = tmp_path / "again" / "sheets"
    lines2, _ = ca.run(TODAY, sheets, md, tmp_path / "again" / "ledger.csv", tmp_path / "again" / "o2", 30, True)
    assert lines2[0].startswith("AWARDS COVERAGE: 2 of 2") and "0 are NOT; 0 only under the other market" in lines2[0], "the sibling row now counts as the award being in the queue"
    assert any("0 added" in l for l in lines2) and len(read(md / "Awards_input.csv")) == 4


def test_dry_run_writes_nothing_to_the_list_and_drafts_the_request(tmp_path):
    lines, md, out, _ = go(tmp_path, arnica=[{"AWARD": "Brand New Award", "SUBMISSION URL": "https://bn.example/enter", "LOCATION": "Berlin, Germany"}])
    assert lines[0].startswith("AWARDS COVERAGE: 1 of 2") and any(l.startswith("AWARDS AUTOADD: mode=dry-run; 1 to add, 0 held") for l in lines)
    assert len(read(md / "Awards_input.csv")) == 2, "dry run: the list is untouched"
    req = (out / f"request_to_upstream_awards_{TODAY}.md").read_text(encoding="utf-8")
    assert "Brand New Award" in req and "nothing is sent by code" in req


def test_apply_appends_blank_id_rows_proves_old_rows_unchanged_and_never_mints_an_id(tmp_path):
    arn = [{"AWARD": "Brand New Award", "SUBMISSION URL": "https://bn.example/enter", "LOCATION": "Not applicable / no physical event location", "PRIORITY": "High", "SUBMISSION DEADLINE": "01/01/2020"}]
    sheets, md, led = world(tmp_path, arnica=arn)
    before = read(md / "Awards_input.csv")
    raw_before = (md / "Awards_input.csv").read_bytes()
    lines, _ = ca.run(TODAY, sheets, md, led, tmp_path / "out", 30, True)
    after = read(md / "Awards_input.csv")
    assert after[:len(before)] == before and len(after) == len(before) + 1, "old rows unchanged, exactly one added"
    new = after[-1]
    assert (new["CONFERENCE"], new["Market"], new["OPPORTUNITY_TYPE"], new["RESEARCH STATUS"]) == ("Brand New Award", "Cybersecurity", "Awards", "Needs Verification")
    assert new["EVENT_ID_CANON"] == "" and new["SOURCE_SHEET"] == "Arnica:2" and new["OPERATOR"] == "bn.example"
    assert new["LOCATION"] == "" and new["SUBMISSION DEADLINE"] == "" and new["PRIORITY"] == "", "no placeholder location; the customer's own dates and priority stay on their sheet"
    assert raw_before.startswith(b"\xef\xbb\xbf") and (md / "Awards_input.csv").read_bytes().startswith(b"\xef\xbb\xbf") and b"\r\n" in (md / "Awards_input.csv").read_bytes()
    assert list(md.glob("Awards_input.pre-customerrows-*.bak.csv")), "the existing writer's backup"
    assert any(l.startswith("AWARDS AUTOADD: mode=applied; 1 added") and "0 customer awards NOT in the queue" in l for l in lines)
    lines2, _ = ca.run(TODAY, sheets, md, led, tmp_path / "out", 30, True)
    assert any(l.startswith("AWARDS AUTOADD: mode=applied; 0 added") for l in lines2) and len(read(md / "Awards_input.csv")) == len(before) + 1


def test_a_name_already_on_the_list_in_any_market_is_never_added_again_even_with_a_new_url(tmp_path):
    inp = [{"CONFERENCE": "Same Name Award", "SUBMISSION URL": "https://old.example/a", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-same-nan-awards"}]
    arn = [{"AWARD": "same name award", "SUBMISSION URL": "https://different.example/b"}]
    lines, md, out, _ = go(tmp_path, arnica=arn, inputs=inp, apply=True)
    assert len(read(md / "Awards_input.csv")) == 3 and any("0 added" in l for l in lines)


def test_the_cap_adds_nothing_for_a_market_whose_sheet_changed_shape(tmp_path):
    arn = [{"AWARD": f"Award Number {i}", "SUBMISSION URL": f"https://a{i}.example/enter"} for i in range(5)]
    lines, md, out, _ = go(tmp_path, arnica=arn, inputs=[], apply=True, cap=3)
    assert len(read(md / "Awards_input.csv")) == 2, "nothing added"
    assert any(l.startswith("AWARDS AUTOADD: mode=applied; 0 added, 5 held") for l in lines)
    assert "cap: 5 awards for Cybersecurity" in (out / "awards_auto_add.json").read_text(encoding="utf-8")
    assert any(l.startswith("AWARDS AUTOADD NOT PICKED UP: Award Number 0") for l in lines)


def test_the_same_award_twice_on_the_customers_sheet_is_added_once(tmp_path):
    arn = [{"AWARD": "Twice Award", "SUBMISSION URL": "https://t.example/a"}, {"AWARD": "Twice Award (2026)", "SUBMISSION URL": "https://t.example/b"}]
    lines, md, out, _ = go(tmp_path, arnica=arn, apply=True)
    assert [r["CONFERENCE"] for r in read(md / "Awards_input.csv")][2:] == ["Twice Award"]
    assert "lists this award twice" in (out / "awards_auto_add.json").read_text(encoding="utf-8")


def test_a_missing_snapshot_or_list_is_reported_as_unknown_never_raised(tmp_path):
    lines, code = ca.run(TODAY, tmp_path / "nowhere", tmp_path / "nomarkets", tmp_path / "l.csv", tmp_path / "o", 30, False)
    assert code == 0 and lines[0].startswith("AWARDS COVERAGE: UNKNOWN")
    sheets, md, led = world(tmp_path)
    (sheets / "utility-awards.csv").unlink()
    lines, code = ca.run(TODAY, sheets, md, led, tmp_path / "o", 30, False)
    assert lines[0].startswith("AWARDS COVERAGE: UNKNOWN - no snapshot of the utility-awards sheet")


def test_apply_on_the_live_markets_folder_is_refused_without_the_reviewers_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["customer_awards.py", "--apply", "--markets-dir", str(ca.MARKETS)])
    assert ca.main() == 0
    assert "REFUSED" in capsys.readouterr().out


def test_the_newest_snapshot_in_the_store_is_the_one_read(tmp_path):
    for stamp in ("20261003-020042", "20261010-152118", "20261010-062042"):
        d = tmp_path / "utility-awards"
        d.mkdir(exist_ok=True)
        (d / f"utility-awards_{stamp}.csv").write_text("AWARD\n", encoding="utf-8")
    assert ca.newest_sheet(tmp_path, "utility-awards").name == "utility-awards_20261010-152118.csv"


# ---------------------------------------------------------------- ACT-67 follow-up 2: UN-LABEL the DUP_OF rows the customer lists
def unlabel_world(tmp_path):
    inp = [{"CONFERENCE": "Fortress Award", "SUBMISSION URL": "https://bi.example/fortress", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-fortress-award-nan-awards"},
           {"CONFERENCE": "Fortress Award (Business Intelligence Group)", "SUBMISSION URL": "https://bi.example/fortress2", "Market": "Cybersecurity", "DUP_OF": "Fortress Award",
            "EVENT_ID_CANON": "2026-fortress-award-nan-awards"},                                    # carries the survivor's id: must be blanked
           {"CONFERENCE": "Not Listed Award", "SUBMISSION URL": "https://nl.example/a", "Market": "Cybersecurity", "DUP_OF": "Fortress Award"},      # the customer does not list it: untouched
           {"CONFERENCE": "Sibling Award", "SUBMISSION URL": "https://sb.example/a", "Market": "Cybersecurity", "DUP_OF": "MARKET_SIBLING", "EVENT_ID_CANON": "2027-sibling-nan-awards"},
           {"CONFERENCE": "Twice Award 2026", "SUBMISSION URL": "https://tw.example/a", "Market": "Utility", "EVENT_ID_CANON": "2026-twice-nan-awards"},
           {"CONFERENCE": "Twice Award 2026", "SUBMISSION URL": "https://tw.example/a", "Market": "Utility", "DUP_OF": "Utility Global:5", "EVENT_ID_CANON": "2026-twice-nan-awards"}]   # same name as a live row
    arn = [{"AWARD": "Fortress Award", "SUBMISSION URL": "https://bi.example/fortress"}, {"AWARD": "Fortress Award (Business Intelligence Group)", "PRIORITY": "High", "SUBMISSION URL": "https://bi.example/fortress2"},
           {"AWARD": "Sibling Award", "SUBMISSION URL": "https://sb.example/a"}]
    util = [{"AWARD": "Twice Award", "SUBMISSION URL": "https://tw.example/a"}]
    return world(tmp_path, arnica=arn, utility=util, inputs=inp)


def test_unlabel_dry_run_names_what_it_would_clear_and_changes_nothing(tmp_path):
    sheets, md, led = unlabel_world(tmp_path)
    before = (md / "Awards_input.csv").read_bytes()
    lines = ca.run_unlabel(TODAY, sheets, md, tmp_path / "out", False)
    assert lines == ["AWARDS UNLABEL: mode=dry-run; 1 to clear (1 also lose a copied id); 2 left labelled (reasons in awards_unlabel.md)"]
    assert (md / "Awards_input.csv").read_bytes() == before
    text = (tmp_path / "out" / "awards_unlabel.md").read_text(encoding="utf-8")
    assert "Fortress Award (Business Intelligence Group)" in text and "High" in text and "the customer's sheet for this market does not list it" in text
    assert "Twice Award 2026" in text and "the customer lists it twice" in text, "a same-name twin is already researched and shown; un-labelling it would only collide"
    assert "Sibling Award" not in text, "MARKET_SIBLING rows are never touched or even listed"


def test_unlabel_apply_changes_exactly_the_dup_of_and_the_copied_id_proves_it_and_a_second_apply_changes_nothing(tmp_path):
    sheets, md, led = unlabel_world(tmp_path)
    old = read(md / "Awards_input.csv")
    assert ca.run_unlabel(TODAY, sheets, md, tmp_path / "out", True)[0].startswith("AWARDS UNLABEL: mode=applied; 1 cleared (1 also lose a copied id)")
    new = read(md / "Awards_input.csv")
    changed = {(i, c) for i, (a, b) in enumerate(zip(old, new)) for c in a if a[c] != b[c]}
    assert changed == {(3, "DUP_OF"), (3, "EVENT_ID_CANON")} and len(new) == len(old)
    assert new[3]["EVENT_ID_CANON"] == "" and new[2]["EVENT_ID_CANON"] == "2026-fortress-award-nan-awards", "the survivor keeps its id; the un-labelled row waits for its OWN (nothing is minted)"
    assert new[5]["DUP_OF"] == "MARKET_SIBLING" and new[4]["DUP_OF"] == "Fortress Award"
    assert list(md.glob("Awards_input.pre-unlabel-*.bak.csv"))
    assert ca.run_unlabel(TODAY, sheets, md, tmp_path / "out2", True)[0].startswith("AWARDS UNLABEL: mode=applied; 0 cleared")
    assert read(md / "Awards_input.csv") == new


def test_an_unlabelled_row_that_keeps_its_own_distinct_id_keeps_it(tmp_path):
    inp = [{"CONFERENCE": "Alpha Award", "SUBMISSION URL": "https://a.example/x", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-alpha-nan-awards"},
           {"CONFERENCE": "Alpha Award (Other Body)", "SUBMISSION URL": "https://a.example/y", "Market": "Cybersecurity", "DUP_OF": "Alpha Award", "EVENT_ID_CANON": "2026-alpha-other-nan-awards"}]
    sheets, md, led = world(tmp_path, arnica=[{"AWARD": "Alpha Award (Other Body)", "SUBMISSION URL": "https://a.example/y"}], inputs=inp)
    ca.run_unlabel(TODAY, sheets, md, tmp_path / "out", True)
    assert read(md / "Awards_input.csv")[3]["EVENT_ID_CANON"] == "2026-alpha-other-nan-awards"


def test_unlabel_on_the_live_markets_folder_needs_the_reviewers_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["customer_awards.py", "--unlabel", "--apply", "--markets-dir", str(ca.MARKETS)])
    assert ca.main() == 0
    assert "AWARDS UNLABEL: REFUSED" in capsys.readouterr().out


def test_the_request_draft_asks_for_the_own_id_names_the_close_award_and_is_plain_ascii(tmp_path):
    inp = [{"CONFERENCE": "Fortress Award", "SUBMISSION URL": "https://bi.example/fortress", "Market": "Cybersecurity", "EVENT_ID_CANON": "2026-fortress-award-nan-awards"},
           {"CONFERENCE": "Fortress Award (Business Intelligence Group)", "SUBMISSION URL": "https://bi.example/fortress2", "Market": "Cybersecurity"},
           {"CONFERENCE": "TIME / Statista America\u2019s Top GreenTech", "SUBMISSION URL": "https://time.example/x", "Market": "Utility"}]
    draft = ca.request_draft(TODAY, ca.waiting_for_id(inp), inp)
    assert "same website/award as Fortress Award?" in draft and "OWN permanent EVENT_ID" in draft and "which id" in draft
    assert draft.isascii() and "America's Top GreenTech" in draft
    assert ca.ascii_text("a\u2013b \u201cq\u201d \u00e9") == 'a-b "q" e'
