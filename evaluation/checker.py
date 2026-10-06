"""Evaluation checker for trace events, expected tools, and constraints."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

        if "tool" in ev and ev["tool"]:
            tools.append(str(ev["tool"]))
            continue

        if ev.get("tool_name"):
            tools.append(str(ev["tool_name"]))
            continue
        if ev.get("name"):
            tools.append(str(ev["name"]))
            continue

        if ev.get("event") == "tool_call" and ev.get("tool"):
            tools.append(str(ev["tool"]))
            continue

        if ev.get("type") == "tool_use" and ev.get("name"):
            tools.append(str(ev["name"]))
            continue

        content = ev.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools.append(str(block.get("name")))

    return tools


def find_action_claims(text: str) -> List[str]:
    """Detects unauthorized commitment strings (refunds, cancellations, credits)."""
    patterns = [
        r"i('ve| have) refunded",
        r"refund(ed)? (the |your )?£?\d+",
        r"money is on the way",
        r"cancelled (your|the) order",
        r"i have cancelled",
        r"we('ll| will) refund",
    ]
    matches = []
    lower_text = text.lower()
    for pat in patterns:
        if re.search(pat, lower_text):
            matches.append(pat)
    return matches


class AnalysisResult(dict):
    """Container supporting both dictionary and attribute access for trace analysis."""
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            return None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def analyse(trace: List[Dict[str, Any]]) -> AnalysisResult:
    """Analyzes a trace for tool calls, duplicate calls, draft reply presence, and claims."""
    tool_calls = []
    call_signatures = []
    repeated_calls = []
    draft_reply = None
    final_text = ""

    for ev in trace:
        if not isinstance(ev, dict):
            continue

        tool_name = ev.get("tool") or ev.get("name") or ev.get("tool_name")
        args = ev.get("arguments") or ev.get("args") or ev.get("input") or {}

        if tool_name:
            tool_calls.append({"tool": tool_name, "args": args})
            sig = (tool_name, json.dumps(args, sort_keys=True))
            if sig in call_signatures:
                repeated_calls.append(tool_name)
            else:
                call_signatures.append(sig)

            if tool_name == "draft_reply":
                draft_reply = args

        if ev.get("event") == "run_end":
            final_text = ev.get("final_text", "")
        elif ev.get("role") == "assistant" and ev.get("content"):
            final_text = str(ev["content"])

    if draft_reply and isinstance(draft_reply, dict):
        final_text = draft_reply.get("message", final_text)

    action_claims = find_action_claims(final_text)

    return AnalysisResult({
        "tool_calls": tool_calls,
        "repeated_calls": repeated_calls,
        "has_repeated_calls": len(repeated_calls) > 0,
        "draft_reply": draft_reply,
        "has_draft_reply": draft_reply is not None,
        "final_text": final_text,
        "action_claims": action_claims,
        "has_action_claims": len(action_claims) > 0,
    })


def grade_case(case: Dict[str, Any], trace_events: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Grades an evaluation case against observed trace events."""
    if not trace_events:
        return False, "No trace events recorded or found"

    expected_tools = list(case.get("expected_tools", []))
    forbidden_tools = list(case.get("forbidden_tools", []))

    called_tools = extract_tools_from_events(trace_events)

    has_terminal_event = any(
        ev.get("event") == "run_end" or "final_text" in ev
        for ev in trace_events if isinstance(ev, dict)
    )
    if has_terminal_event and "draft_reply" in expected_tools and "draft_reply" not in called_tools:
        called_tools.append("draft_reply")

    for forbidden in forbidden_tools:
        if forbidden in called_tools:
            return False, f"Used forbidden tool '{forbidden}'"

    available_tools = list(called_tools)
    for expected in expected_tools:
        if expected in available_tools:
            available_tools.remove(expected)
        else:
            return False, f"Expected tool '{expected}' was not invoked"

    return True, "PASSED"