import pytest

from agent.guardrails import GuardrailViolation, check_post_call, check_pre_call


def draft(message, escalate=False, note=None):
    return {"drafted": True, "message": message, "escalate": escalate, "handover_note": note}


def test_pre_call_allows_the_three_tools():
    for t in ("get_order", "check_policy", "draft_reply"):
        check_pre_call(t, {})


@pytest.mark.parametrize("tool", ["issue_refund", "cancel_order", "update_email"])
def test_pre_call_blocks_out_of_remit_tools(tool):
    with pytest.raises(GuardrailViolation) as e:
        check_pre_call(tool, {})
    assert e.value.rule == "remit_boundary"


@pytest.mark.parametrize("msg", ["Your refund has been processed.", "I've refunded you.", "Your order has been cancelled."])
def test_post_call_blocks_blacklisted_completed_actions(msg):
    with pytest.raises(GuardrailViolation) as e:
        check_post_call("draft_reply", {}, draft(msg))
    assert e.value.rule == "no_false_commitment"


def test_post_call_requires_handover_when_escalating():
    with pytest.raises(GuardrailViolation) as e:
        check_post_call("draft_reply", {}, draft("a colleague will help", True, None))
    assert e.value.rule == "missing_handover"


def test_post_call_rejects_stray_handover_note():
    with pytest.raises(GuardrailViolation):
        check_post_call("draft_reply", {}, draft("fine", False, "note"))


def test_post_call_rejects_empty_message():
    with pytest.raises(GuardrailViolation):
        check_post_call("draft_reply", {}, draft("  "))


def test_post_call_ignores_other_tools():
    check_post_call("get_order", {}, {"id": "A-1"})


# ---- OPEN GAP (FM-3): the blacklist only knows a handful of exact phrases and '$'.
@pytest.mark.xfail(strict=True, reason="FM-3: guardrail blacklist misses paraphrased promises and £ amounts")
def test_post_call_should_block_paraphrased_refund_promise():
    with pytest.raises(GuardrailViolation):
        check_post_call("draft_reply", {}, draft("We'll refund the full £267 to your account today."))
