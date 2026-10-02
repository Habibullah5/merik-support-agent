import json

import agent.loop as loop_mod
from scripted.golden import call, reply, turn

GOOD = reply("Order A-91 was delivered on 1 Sep.")


def events(trace):
    return [r["event"] for r in trace if r["step"] > 0 and r["event"] != "run_end"]


def test_draft_reply_ends_the_run_and_unused_turns_are_never_requested(run):
    res, trace, client = run([turn(GOOD), turn(call("get_order", order_id="A-11"))])
    assert res["stop_reason"] == "draft_reply"
    assert res["final_text"] == "Order A-91 was delivered on 1 Sep."
    assert len(client.requests) == 1


def test_trace_has_header_steps_and_end(run):
    res, trace, _ = run([turn(call("get_order", order_id="A-91")), turn(GOOD)])
    assert trace[0]["event"] == "run_start" and trace[0]["step"] == 0
    assert trace[0]["model"] == "scripted" and trace[0]["today"] == "2026-09-10"
    assert [r["step"] for r in trace[1:-1]] == [1, 2]
    assert trace[-1]["event"] == "run_end" and trace[-1]["stop_reason"] == "draft_reply"
    for r in trace[1:-1]:
        assert {"tool", "arguments", "result_summary", "duration_ms", "cost_usd"} <= r.keys()


def test_sender_is_passed_with_the_message(run):
    _, _, client = run([turn(GOOD)], sender="Hina Qureshi", message="Where is A-37?")
    first = client.requests[0]["messages"][0]["content"]
    assert first == "Sender: Hina Qureshi\nMessage: Where is A-37?"
    assert "Thursday 10 September 2026" in client.requests[0]["system"]


def test_empty_message_is_marked_not_blank(run):
    _, _, client = run([turn(GOOD)], message="")
    assert "(empty message)" in client.requests[0]["messages"][0]["content"]


def test_step_cap(run):
    script = [turn(call("get_order", order_id=i)) for i in ("A-11", "A-23", "A-58")]
    res, trace, _ = run(script, max_steps=2)
    assert res["stop_reason"] == "step_cap"
    assert "stop_step_cap" in events(trace)


def test_spend_cap(run, monkeypatch):
    monkeypatch.setattr(loop_mod, "estimate_cost_usd", lambda i, o: 1.0)
    res, trace, _ = run([turn(call("get_order", order_id="A-91")), turn(GOOD)], max_spend_usd=0.5)
    assert res["stop_reason"] == "spend_cap"
    assert "stop_spend_cap" in events(trace)


def test_out_of_remit_tool_is_blocked_and_never_executed(run):
    res, trace, _ = run([turn(call("issue_refund", order_id="A-91", amount=500)), turn(GOOD)])
    blocked = [r for r in trace if r["event"] == "guardrail_blocked"]
    assert len(blocked) == 1 and blocked[0]["result"]["rule"] == "remit_boundary"
    assert res["stop_reason"] == "draft_reply"


def test_blocked_draft_is_discarded_and_model_can_retry(run):
    script = [turn(reply("I've refunded you.")), turn(reply("A colleague will look at your refund.", True, "A-91 refund"))]
    res, trace, _ = run(script)
    assert [r["event"] for r in trace if r["step"] > 0 and r["event"] != "run_end"] == ["guardrail_blocked", "tool_call"]
    assert res["draft"]["escalate"] is True


def test_tool_exception_is_returned_to_the_model_not_raised(run):
    res, trace, _ = run([turn(call("get_order", wrong_arg="x")), turn(GOOD)])
    assert "tool_failed" in trace[1]["result"]["error"]
    assert res["stop_reason"] == "draft_reply"


def test_cost_is_attributed_to_the_first_record_of_a_turn(run, monkeypatch):
    monkeypatch.setattr(loop_mod, "estimate_cost_usd", lambda i, o: 0.01)
    _, trace, _ = run([turn(call("get_order", order_id="A-91"), call("get_order", order_id="A-23")), turn(GOOD)])
    costs = [r["cost_usd"] for r in trace if r["event"] == "tool_call"]
    assert costs == [0.01, 0.0, 0.01]


def test_max_steps_zero_is_respected_not_replaced_by_default(run):
    res, _, _ = run([turn(GOOD)], max_steps=0)
    assert res["stop_reason"] == "step_cap"


# ---- OPEN GAP (FM-2): a plain-text ending is accepted as the final reply.
def test_plain_text_ending_is_recorded_as_final_answer(run):
    res, trace, _ = run([{"text": "Your order shipped."}])
    assert res["stop_reason"] == "final_answer" and res["draft"] is None


import pytest  # noqa: E402


@pytest.mark.xfail(strict=True, reason="FM-2: run can end without a draft_reply (no escalation, no handover)")
def test_every_run_should_end_with_a_draft_reply(run):
    res, _, _ = run([{"text": "Your order shipped."}, turn(reply("Your order shipped."))])
    assert res["stop_reason"] == "draft_reply"
