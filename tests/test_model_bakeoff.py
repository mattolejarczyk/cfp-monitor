"""ACT-56: the bake-off's blind request, scoring, registry write and compare output. No network, no model call."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.model_bakeoff import bakeoff_lib as B      # noqa: E402
from experiments.model_bakeoff import compare as C          # noqa: E402
from experiments.model_bakeoff import registry as R         # noqa: E402

PAGE = "Join us at Test Conf. The conference will be held on January 26-27, 2027 in Vienna, Austria."
JOB = {"id": "read::t", "kind": "read", "event": "Test Conf 2027", "edition": "2027", "text": PAGE, "system": "SYS",
       "facts": [{"field": "start_date", "gold": "2027-01-26"}, {"field": "city", "gold": "Vienna"}]}


def result(parsed, status=200):
    return {"parsed": parsed, "raw": json.dumps(parsed), "cost": 0.001, "seconds": 2.0, "status": status, "error": "", "tokens_in": 100, "tokens_out": 20}


GOOD = {"start_date": {"value": "2027-01-26", "quote": "held on January 26-27, 2027"}, "city": {"value": "Vienna", "quote": "in Vienna, Austria"}}
WRONG = {"start_date": {"value": "2027-01-27", "quote": "held on January 26-27, 2027"}, "city": {"value": "", "quote": ""}}
FAKE = {"start_date": {"value": "2027-01-26", "quote": "the conference starts January 26, 2027"}, "city": {"value": "", "quote": ""}}


def test_request_is_single_turn_and_blind():
    msgs = B.blind_messages("SYS", "Test Conf 2027", "2027", PAGE)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert "2027-01-26" not in msgs[0]["content"] + msgs[1]["content"].split("PAGE TEXT:")[0]
    with pytest.raises(ValueError):
        B.assert_blind(msgs + [{"role": "assistant", "content": "earlier answer"}], "2027")
    with pytest.raises(ValueError):                                   # a date leaked into the header is refused
        B.assert_blind([{"role": "system", "content": "s"}, {"role": "user", "content": "EVENT: X 2031\nEDITION YEAR TO REPORT: 2027\n\nPAGE TEXT:\nabc"}], "2027")


def test_builder_signature_takes_no_key_value():
    import inspect
    assert list(inspect.signature(B.blind_messages).parameters) == ["system", "event", "edition", "page_text", "cap"]


def test_registry_append_only_and_verdicts(tmp_path):
    reg, pages = tmp_path / "reg.jsonl", tmp_path / "pages"
    msgs = B.blind_messages("SYS", JOB["event"], JOB["edition"], JOB["text"])
    rows = R.append_rows("ds", "ds-1", JOB, msgs, result(GOOD), reg, pages)
    assert [r["verdict"] for r in rows] == ["correct", "correct"] and all(r["quote_verbatim_on_page"] for r in rows)
    first = reg.read_text(encoding="utf-8")
    R.append_rows("ds", "ds-2", JOB, msgs, result(WRONG), reg, pages)
    assert reg.read_text(encoding="utf-8").startswith(first)         # earlier rows untouched; new rows appended
    got = R.read(reg)
    assert len(got) == 4
    assert [r["verdict"] for r in got[2:]] == ["wrong-accepted", "missed"]
    assert got[0]["raw_response"] and got[0]["page_sha"] and (pages / f"{got[0]['page_sha']}.txt").read_text(encoding="utf-8") == PAGE
    assert {"run_id", "ts", "model_id", "route", "effort", "role", "job", "fact", "prompt_sha", "key_value", "tokens_in", "tokens_out", "cost_usd", "latency_s", "error"} <= set(got[0])


def test_unquoted_claim_is_not_accepted_and_failed_call_is_not_scored(tmp_path):
    reg = tmp_path / "r.jsonl"
    msgs = B.blind_messages("SYS", JOB["event"], JOB["edition"], JOB["text"])
    rows = R.append_rows("ds", "ds-3", JOB, msgs, result(FAKE), reg, tmp_path / "p")
    assert rows[0]["accepted"] == "" and rows[0]["verdict"] == "missed" and not rows[0]["quote_verbatim_on_page"]
    rows = R.append_rows("ds", "ds-4", JOB, msgs, result(None, status=429), reg, tmp_path / "p")
    assert {r["verdict"] for r in rows} == {"call-failed"}


def test_blank_key_wrong_accept():
    assert R.verdict({"gold": "", "accepted": "2027-01-26", "field": "start_date"}) == "wrong-accepted"
    assert R.verdict({"gold": "", "accepted": "", "field": "start_date"}) == "correct-blank"


def test_compare_summary_and_second_opinion(tmp_path):
    reg = tmp_path / "r.jsonl"
    msgs = B.blind_messages("SYS", JOB["event"], JOB["edition"], JOB["text"])
    R.append_rows("ds", "ds-1", JOB, msgs, result(GOOD), reg, tmp_path / "p")
    R.append_rows("ds", "ds-2", JOB, msgs, result(WRONG), reg, tmp_path / "p")
    R.append_rows("nemo", "nemo-1", JOB, msgs, result(WRONG), reg, tmp_path / "p")
    rows = R.read(reg)
    s = C.summarise(rows)
    assert s["ds"]["runs"] == 2 and s["ds"]["wrong_accepted"] == 1 and s["ds"]["precision"] == round(2 / 3, 3)
    assert s["ds"]["stable_every_run"] == 0 and s["ds"]["found_any_run"] == 2          # start_date and city each found in one of two runs
    assert s["nemo"]["wrong_accepted"] == 1 and s["nemo"]["cost_usd"] == 0.001
    so = C.second_opinion(rows, "ds", "nemo")                                          # ds run 1 is GOOD, nemo is WRONG: a conflict on start_date, city only ds
    assert so["conflict"] == 1 and so["only_a"] == 1 and so["agree"] == 0
    assert C.select(rows, models=["nemo"]) == [r for r in rows if r["model_key"] == "nemo"]
    assert C.select(rows, runs=["ds-1"]) and all(r["run_id"] == "ds-1" for r in C.select(rows, runs=["ds-1"]))


def test_compare_cli_prints_side_by_side(tmp_path, capsys):
    reg = tmp_path / "r.jsonl"
    msgs = B.blind_messages("SYS", JOB["event"], JOB["edition"], JOB["text"])
    R.append_rows("ds", "ds-1", JOB, msgs, result(GOOD), reg, tmp_path / "p")
    R.append_rows("nemo", "nemo-1", JOB, msgs, result(WRONG), reg, tmp_path / "p")
    C.main(["--registry", str(reg), "--models", "ds,nemo", "--second-opinion", "ds", "nemo"])
    out = capsys.readouterr().out
    assert "KEY='2027-01-26'" in out and "verdict=correct" in out and "verdict=wrong-accepted" in out and "PER-MODEL SUMMARY" in out and "SECOND OPINION" in out


def test_models_config_needs_no_code_to_add():
    m = B.load_models()
    assert {"ds", "nemo", "bunny", "luna", "sol"} <= set(m)
    for v in m.values():
        assert {"id", "route", "effort", "price_source", "price_date"} <= set(v) and v["route"] in ("openrouter", "codex")
    assert m["luna"]["effort"] == "max" and m["sol"]["effort"] == "max"


def test_codex_command_is_fresh_and_explicit(monkeypatch, tmp_path):
    seen = {}

    class P:
        returncode, stdout, stderr = 0, "tokens used\n12,345\n", ""

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_text('{"start_date": {"value": "", "quote": ""}}', encoding="utf-8")
        return P()
    monkeypatch.setattr(B.subprocess, "run", fake_run)
    monkeypatch.setattr(B, "CODEX_LOG", tmp_path / "codex.jsonl")
    r = B.codex_ask("gpt-6-luna", B.blind_messages("SYS", "E", "2027", PAGE), "t")
    cmd = seen["cmd"]
    assert "resume" not in cmd and "--ephemeral" in cmd and cmd[cmd.index("-m") + 1] == "gpt-6-luna" and "model_reasoning_effort=max" in cmd
    assert r["tokens"] == 12345 and "-" == cmd[-1]


def test_codex_failure_raises_with_exact_text(monkeypatch, tmp_path):
    class P:
        returncode, stdout, stderr = 1, "", "ERROR: usage limit reached"
    monkeypatch.setattr(B.subprocess, "run", lambda cmd, **kw: P())
    monkeypatch.setattr(B, "CODEX_LOG", tmp_path / "codex.jsonl")
    with pytest.raises(B.CodexError, match="usage limit reached"):
        B.codex_ask("gpt-6-sol", B.blind_messages("SYS", "E", "2027", PAGE), "t")
