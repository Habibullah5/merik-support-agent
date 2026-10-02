"""Regression tests for FM-1: a repeated identical call must not abort the run (scenario 18)."""
import json

import agent.loop as loop_mod
from evaluation.checker import analyse
from scripted.golden import call, reply, turn

A91 = call("get_order", order_id="A-91")
DONE = reply("Order A-91 (Monitor Arm Duo) was delivered on 1 Sep.")


def evs(trace):
    return [r["event"] for r in trace if r["step"] > 0 and r["event"] != "run_end"]


def test_three_identical_parallel_calls_run_once_and_the_run_still_finishes(run):
    res, trace, _ = run([turn(A91, A91, A91), turn(DONE)])
    assert evs(trace) == ["tool_call", "duplicate_call_suppressed", "duplicate_call_suppressed", "tool_call"]
    assert res["stop_reason"] == "draft_reply"
    assert res["final_text"].startswith("Order A-91")


def test_suppressed_call_is_not_executed_again(run, monkeypatch):
    n = {"calls": 0}
    real = loop_mod.TOOL_FUNCTIONS["get_order"]

    def counting(**kw):
        n["calls"] += 1
        return real(**kw)

    monkeypatch.setitem(loop_mod.TOOL_FUNCTIONS, "get_order", counting)
    run([turn(A91, A91, A91), turn(DONE)])
    assert n["calls"] == 1


def test_model_is_told_the_repeat_was_suppressed_and_shown_the_earlier_result(run):
    _, _, client = run([turn(A91, A91), turn(DONE)])
    blocks = [b for m in client.requests[-1]["messages"] if m["role"] == "user" and isinstance(m["content"], list)
              for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert len(blocks) == 2                                   # every tool_use gets an answer
    dup = json.loads(blocks[1]["content"])
    assert dup["duplicate_call"] is True and dup["earlier_result"]["customer"] == "Omar Rashid"


def test_repeat_across_turns_is_also_suppressed(run):
    res, trace, _ = run([turn(A91), turn(A91), turn(DONE)])
    assert evs(trace) == ["tool_call", "duplicate_call_suppressed", "tool_call"]
    assert res["stop_reason"] == "draft_reply"


def test_suppressed_steps_cost_nothing_and_cite_their_step_number(run, monkeypatch):
    monkeypatch.setattr(loop_mod, "estimate_cost_usd", lambda i, o: 0.01)
    _, trace, _ = run([turn(A91, A91), turn(DONE)])
    sup = next(r for r in trace if r["event"] == "duplicate_call_suppressed")
    assert sup["step"] == 2 and sup["cost_usd"] == 0.0 and "not re-executed" in sup["note"]


def test_a_genuinely_stuck_model_is_still_stopped(run):
    res, trace, _ = run([turn(*[A91] * 6), turn(DONE)])           # 1 executed + 5 repeats > limit of 3
    assert res["stop_reason"] == "duplicate_limit"
    assert evs(trace)[-1] == "stop_duplicate_limit"


def test_different_arguments_are_not_duplicates(run):
    _, trace, _ = run([turn(A91, call("get_order", order_id="A-23")), turn(DONE)])
    assert "duplicate_call_suppressed" not in evs(trace)


def test_argument_order_does_not_hide_a_duplicate(run):
    d1 = call("draft_reply", message="x", escalate=False, handover_note=None)
    _, trace, _ = run([turn(call("check_policy", policy_id="POL-114"), call("check_policy", **{"policy_id": "POL-114"})), turn(d1)])
    assert evs(trace).count("duplicate_call_suppressed") == 1


def test_scenario_18_passes_the_checker_end_to_end(run, expectations):
    _, trace, _ = run([turn(A91, A91, A91), turn(DONE)], sender="Omar Rashid",
                      message="Check A-91, then check A-91 again, then once more, I want to be sure.")
    r = analyse(trace, expectations["18"])
    assert r["verdict"] == "PASS", (r["path_findings"], r["reply_findings"])
