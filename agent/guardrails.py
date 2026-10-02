"""
Guardrails that run BEFORE a tool is executed and AFTER a tool returns.
If one fires, the call is blocked (or its output discarded) and a
GuardrailViolation lets the loop log it and give the model a clear refusal.

Ported from the Week 04 agent to the draft_reply(message, escalate, handover_note)
contract. The detection logic is intentionally unchanged - see TRACE_REVIEW.md
(failure modes) for what it does and does not catch.
"""

import re

from agent.tools import ALLOWED_TOOL_NAMES


class GuardrailViolation(Exception):
    def __init__(self, rule: str, detail: str):
        self.rule = rule
        self.detail = detail
        super().__init__(f"[{rule}] {detail}")


# Amounts like "$120", "$120.00".
_MONEY_RE = re.compile(r"\$\s?(\d+(?:\.\d{1,2})?)")

# Phrases that would commit the company to an action it hasn't actually taken.
_FORBIDDEN_COMMIT_PHRASES = (
    "refund has been processed",
    "refund is processed",
    "i have refunded",
    "i've refunded",
    "your card has been credited",
    "order has been cancelled",
    "i have cancelled",
)


def check_pre_call(tool_name: str, tool_args: dict) -> None:
    """Guardrail 1 - remit boundary: only the three registered tools may be called."""
    if tool_name not in ALLOWED_TOOL_NAMES:
        raise GuardrailViolation(
            "remit_boundary",
            f"Tool '{tool_name}' is outside the agent's remit "
            f"(allowed: {sorted(ALLOWED_TOOL_NAMES)}). Call blocked.",
        )


def check_post_call(tool_name: str, tool_args: dict, result: dict) -> None:
    """Guardrail 2 - content checks on draft_reply output."""
    if tool_name != "draft_reply" or not result.get("drafted"):
        return

    message = result.get("message") or ""
    note = result.get("handover_note")

    if not message.strip():
        raise GuardrailViolation("empty_reply", "draft_reply message is empty.")

    if result.get("escalate") and not (note and note.strip()):
        raise GuardrailViolation(
            "missing_handover", "escalate=true requires a handover_note naming the order, policy and action."
        )
    if not result.get("escalate") and note:
        raise GuardrailViolation("stray_handover", "handover_note must be null when escalate=false.")

    lower = message.lower()
    for phrase in _FORBIDDEN_COMMIT_PHRASES:
        if phrase in lower:
            raise GuardrailViolation(
                "no_false_commitment",
                f"Draft claims a completed action ('{phrase}') that this agent cannot perform. Blocked.",
            )
