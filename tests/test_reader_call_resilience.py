"""experiments/read_the_page_pass/run.py _call: a network error (TLS reset, timeout) is a failed call like a 429: retried, logged, and finally (None, None); never an exception into the caller
(2026-10-05: a 'bad record mac' TLS error ended a whole scored run)."""
import json

from experiments.read_the_page_pass import run as R


def test_a_network_error_is_retried_and_then_reported_as_a_failed_call(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(R, "MAX_REQUESTS", 1000)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    calls = []

    def boom(model, msgs):
        calls.append(1)
        raise ConnectionError("bad record mac")

    monkeypatch.setattr(R.sp, "call_model", boom)
    assert R._call("C", "Some Event", [{"role": "user", "content": "x"}]) == (None, None)
    assert len(calls) == 4                                                       # four attempts, then a failed call
    log = [json.loads(l) for l in (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(log) == 4 and all(l["status"] == "exception ConnectionError" for l in log)


def test_a_good_answer_after_one_error_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LOG", tmp_path / "log.jsonl")
    monkeypatch.setattr(R, "MAX_REQUESTS", 1000)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)

    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"city": {"value": "Oslo", "quote": "Oslo"}}'}}], "usage": {"cost": 0.001}}

    state = {"n": 0}

    def flaky(model, msgs):
        state["n"] += 1
        if state["n"] == 1:
            raise TimeoutError("read timed out")
        return Resp(), 1.0

    monkeypatch.setattr(R.sp, "call_model", flaky)
    out, cost = R._call("C", "E", [{"role": "user", "content": "x"}])
    assert out == {"city": {"value": "Oslo", "quote": "Oslo"}} and cost == 0.001 and state["n"] == 2
