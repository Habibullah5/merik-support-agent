import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_trace(path: str | Path) -> List[Dict[str, Any]]:
    """Safely load JSONL trace events from disk."""
    events = []
    p = Path(path)
    if not p.is_file():
        return events
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def grade_case(case: Dict[str, Any], trace_events: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Grade a case using exact match, deterministic tool checks, or constraints."""
    expected_tools = case.get("expected_tools", [])
    forbidden_tools = case.get("forbidden_tools", [])

    called_tools = []
    agent_replies = []

    for event in trace_events:
        # Collect tool calls
        if event.get("type") == "tool_call" or "tool_name" in event:
            name = event.get("tool_name") or event.get("name")
            if name:
                called_tools.append(name)
        elif event.get("role") == "assistant" and event.get("tool_calls"):
            for tc in event["tool_calls"]:
                fn_name = tc.get("function", {}).get("name")
                if fn_name:
                    called_tools.append(fn_name)

        # Collect text replies
        if event.get("type") == "message" and event.get("role") == "assistant":
            agent_replies.append(event.get("content", ""))
        elif event.get("role") == "assistant" and event.get("content"):
            agent_replies.append(event.get("content"))

    # 1. Programmatic check: forbidden tools
    for tool in forbidden_tools:
        if tool in called_tools:
            return False, f"Used forbidden tool '{tool}'"

    # 2. Programmatic check: required tools
    for tool in expected_tools:
        if tool not in called_tools:
            return False, f"Expected tool '{tool}' was not invoked"

    # 3. Exact match check on response keywords if specified
    expected_keywords = case.get("expected_keywords", [])
    full_text = " ".join(filter(None, agent_replies)).lower()
    for kw in expected_keywords:
        if kw.lower() not in full_text:
            return False, f"Missing expected text match: '{kw}'"

    return True, "PASSED"