"""
The three tools from the scenario pack (section 1).

  get_order(order_id)                          read-only lookup of ONE order id
  check_policy(policy_id)                      read-only policy text
  draft_reply(message, escalate, handover_note) ends the run

Fixture data is loaded from data/*.json (built from docs/merik-support-scenarios.md).
Tools never invent records: unknown ids return the error objects the pack specifies.
"""

import json
import os
import re

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load(name):
    with open(os.path.join(_DATA_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


_ORDERS = _load("orders.json")
_POLICIES = _load("policies.json")
_ORDER_ID_RE = re.compile(r"^A-\d{2}$")  # "Any other id does not exist."


def get_order(order_id: str) -> dict:
    oid = order_id.strip() if isinstance(order_id, str) else ""
    if not _ORDER_ID_RE.match(oid) or oid not in _ORDERS:
        return {"error": "not_found"}
    return dict(_ORDERS[oid])


def check_policy(policy_id: str) -> dict:
    pid = policy_id.strip().upper() if isinstance(policy_id, str) else ""
    if pid not in _POLICIES:
        return {"error": "unknown_policy"}
    return dict(_POLICIES[pid])


def draft_reply(message: str, escalate: bool, handover_note=None) -> dict:
    """Terminal tool. The loop ends the run when this succeeds."""
    return {
        "drafted": True,
        "message": message,
        "escalate": bool(escalate),
        "handover_note": handover_note,
    }


TOOL_FUNCTIONS = {
    "get_order": get_order,
    "check_policy": check_policy,
    "draft_reply": draft_reply,
}
ALLOWED_TOOL_NAMES = frozenset(TOOL_FUNCTIONS)

TOOLS_SCHEMA = [
    {
        "name": "get_order",
        "description": (
            "Look up ONE order by its exact id (format 'A-' plus two digits, e.g. 'A-91'). "
            "USE THIS WHEN: the customer's message names an order id and you need its status, "
            "item, dates, total or notes. "
            "DOES NOT: search by customer name or item, modify anything, or tell you whether the "
            "order belongs to the sender - compare the record's `customer` with the sender yourself. "
            "Returns the order record, or {\"error\": \"not_found\"}. Never call it twice with the same id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Exact order id, e.g. 'A-91'"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "check_policy",
        "description": (
            "Fetch the text of ONE policy by id (POL-101, POL-114, POL-120, POL-133, POL-140, POL-150). "
            "USE THIS WHEN: the request depends on a policy you have not yet read in this run. "
            "DOES NOT: apply the policy to an order - you do that. Fetch only the policies the "
            "request needs, each at most once. Returns the policy text, or {\"error\": \"unknown_policy\"}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"policy_id": {"type": "string", "description": "e.g. 'POL-114'"}},
            "required": ["policy_id"],
        },
    },
    {
        "name": "draft_reply",
        "description": (
            "Write the customer-facing reply. THIS ENDS THE RUN - every run finishes with exactly one "
            "call to it, and you must not write a final answer as plain text instead. "
            "Set escalate=true when a human must act (then handover_note is required: it must name the "
            "order, the policy id and exactly what the human needs to do). Set escalate=false and "
            "handover_note=null when the reply fully resolves the message. "
            "DOES NOT: send anything, refund, cancel, replace or edit anything. The message must never "
            "claim or promise an action you cannot take."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The reply to the customer."},
                "escalate": {"type": "boolean"},
                "handover_note": {
                    "type": ["string", "null"],
                    "description": "For the human agent: order, policy, required action. null when not escalating.",
                },
            },
            "required": ["message", "escalate", "handover_note"],
        },
    },
]
