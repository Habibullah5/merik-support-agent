"""Reproductions of the failure modes named in TRACE_REVIEW.md, using the committed scripts."""
import json
from pathlib import Path

import pytest

from agent.llm import ScriptedClient
from agent.loop import run_agent
from evaluation.checker import analyse, load_trace
from scripted.failure_modes import SCRIPTS

F = json.loads((Path(__file__).resolve().parent.parent / "data/failure_scenarios.json").read_text(encoding="utf-8"))


def tool_results_seen_by_model(client):
    """Everything the model was shown as tool output (messages are recorded by reference, so scan all)."""
    out = []
    for m in client.requests[-1]["messages"]:
        if m["role"] == "user" and isinstance(m["content"], list):
            out += [b["content"] for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    return " ".join(out)


def _run(fid, tmp_path, expectations):
    f = F[fid]
    client = ScriptedClient(SCRIPTS[f["script"]])
    p = tmp_path / f"{fid}.jsonl"
    res = run_agent(f["message"], f["sender"], client=client, scenario=fid, log_path=str(p), verbose=False)
    return res, load_trace(p), analyse(load_trace(p), expectations[str(f["scenario"])]), client


def test_f2_is_a_right_reply_wrong_path_case(tmp_path, expectations):
    _, _, verdict, _ = _run("F2", tmp_path, expectations)
    assert verdict["verdict"] == "PATH FAIL" and verdict["right_reply_wrong_path"]


def test_f3_promise_passes_the_guardrail_but_not_the_checker(tmp_path, expectations):
    res, trace, verdict, _ = _run("F3", tmp_path, expectations)
    assert res["stop_reason"] == "draft_reply"
    assert not [r for r in trace if r["event"] == "guardrail_blocked"]
    assert any("promises an action" in f["msg"] for f in verdict["reply_findings"])


def test_f4_foreign_order_record_reaches_the_model(tmp_path, expectations):
    _, trace, verdict, client = _run("F4", tmp_path, expectations)
    seen_by_model = tool_results_seen_by_model(client)
    assert "Omar Rashid" in seen_by_model            # the loop handed Omar's record to Daniel's run
    assert verdict["verdict"] == "REPLY FAIL"


@pytest.mark.xfail(strict=True, reason="FM-4: loop does not withhold orders that do not belong to the sender")
def test_f4_should_not_expose_foreign_order_to_the_model(tmp_path, expectations):
    _, _, _, client = _run("F4", tmp_path, expectations)
    assert "Omar Rashid" not in tool_results_seen_by_model(client)
