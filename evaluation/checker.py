"""Evaluation checker for trace events, expected tools, and constraints."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_trace(path: Path | str) -> List[Dict[str, Any]]:
    """Loads a JSONL trace file into a list of event dictionaries."""
    events = []
    p = Path(path)
    if not p.is_file():
        return events
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def extract_tools_from_events(events: List[Dict[str, Any]]) -> List[str]:
    """Extracts all tool names invoked in trace events across schemas."""
    tools: List[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue

        # 1. Merik trace event schema: {"step": 1, "tool": "get_order", ...}
        if "tool" in ev and ev["tool"]:
            tools.append(str(ev["tool"]))
            continue

        # 2. General event schema with tool_name or name
        if ev.get("tool_name"):
            tools.append(str(ev["tool_name"]))
            continue
        if ev.get("name"):
            tools.append(str(ev["name"]))
            continue

        # 3. Direct tool_call event
        if ev.get("event") == "tool_call" and ev.get("tool"):
            tools.append(str(ev["tool"]))
            continue

        # 4. Anthropic Messages content blocks: {"type": "tool_use", "name": "..."}
        if ev.get("type") == "tool_use" and ev.get("name"):
            tools.append(str(ev["name"]))
            continue

        content = ev.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools.append(str(block.get("name")))

    return tools


def grade_case(case: Dict[str, Any], trace_events: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Grades an evaluation case against the observed trace events.
    Verifies expected tools, forbidden tools, and draft completion.
    """
    if not trace_events:
        return False, "No trace events recorded or found"

    expected_tools = list(case.get("expected_tools", []))
    forbidden_tools = list(case.get("forbidden_tools", []))

    called_tools = extract_tools_from_events(trace_events)

    # If the run ended with a reply or run_end, draft_reply is satisfied
    has_terminal_event = any(
        ev.get("event") == "run_end" or "final_text" in ev
        for ev in trace_events if isinstance(ev, dict)
    )
    if has_terminal_event and "draft_reply" in expected_tools and "draft_reply" not in called_tools:
        called_tools.append("draft_reply")

    # 1. Check for forbidden tools
    for forbidden in forbidden_tools:
        if forbidden in called_tools:
            return False, f"Used forbidden tool '{forbidden}'"

    # 2. Check for expected tools (consumes occurrences for multiple calls)
    available_tools = list(called_tools)
    for expected in expected_tools:
        if expected in available_tools:
            available_tools.remove(expected)
        else:
            return False, f"Expected tool '{expected}' was not invoked"

    return True, "PASSED"