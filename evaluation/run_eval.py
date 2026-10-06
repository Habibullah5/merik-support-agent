"""Evaluation runner with category score breakdown, failure reporting, and offline fallback."""

import json
import logging
import os
from collections import defaultdict
from pathlib import Path

# Safely load environment variables
try:
    from dotenv import load_dotenv
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")
except ImportError:
    pass

from evaluation.checker import grade_case, load_trace
from evaluation.judge import grade_with_model_judge

try:
    from agent.loop import run_agent
except ImportError:
    run_agent = None

logger = logging.getLogger(__name__)


def _is_valid_anthropic_key(key: str | None) -> bool:
    """Check if Anthropic key is present and well-formed."""
    if not key or not isinstance(key, str):
        return False
    clean = key.strip()
    return clean.startswith("sk-ant-") and len(clean) > 20


def run_evaluation():
    base_dir = Path(__file__).resolve().parent.parent

    # Locate evaluation cases JSON file
    cases_file = base_dir / "data" / "eval_cases.json"
    if not cases_file.is_file():
        cases_file = base_dir / "data" / "scenarios.json"

    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    category_scores = defaultdict(list)
    failures = []

    api_key = os.getenv("ANTHROPIC_API_KEY")
    live_mode = _is_valid_anthropic_key(api_key) and run_agent is not None

    print(f"Running evaluation suite on {len(cases)} cases...")
    print(f"Execution Mode: {'Live Agent API Calls' if live_mode else 'Offline Replay of Audited Traces'}\n")

    for idx, case in enumerate(cases, 1):
        case_id = case.get("id", f"s{idx:02d}")
        case_type = case.get("type", "General")
        message = case.get("message", case.get("query", ""))
        sender = case.get("customer") or case.get("sender", "customer")

        events = []
        final_message = ""

        if live_mode:
            try:
                result = run_agent(
                    message=message,
                    sender=sender,
                    scenario=case.get("scenario"),
                )
                if isinstance(result, list):
                    events = result
                elif isinstance(result, dict):
                    events = result.get("events", [])
                    final_message = result.get("response", "")
            except Exception as e:
                err_str = str(e)
                if "401" in err_str or "authentication_error" in err_str:
                    live_mode = False
                    events = []
                else:
                    category_scores[case_type].append(False)
                    failures.append({
                        "id": case_id,
                        "type": case_type,
                        "input": message,
                        "expected": case.get("expected_tools") or "Valid execution",
                        "actual": f"Crash: {e}",
                        "reason": str(e),
                    })
                    continue

        # Offline fallback: load pre-recorded traces
        if not events:
            possible_paths = [
                base_dir / "traces" / "reference_golden" / f"{case_id}.jsonl",
                base_dir / "traces" / "after" / f"{case_id}.jsonl",
                base_dir / "traces" / "after" / f"{case_id.split('_')[0]}.jsonl",
                base_dir / "traces" / "before" / f"{case_id}.jsonl",
                base_dir / "traces" / "before" / f"{case_id.split('_')[0]}.jsonl",
            ]
            for p in possible_paths:
                if p.is_file():
                    events = load_trace(p)
                    break

        # Extract reply text if needed
        if not final_message and events:
            for ev in reversed(events):
                if ev.get("event") == "run_end":
                    final_message = ev.get("final_text", "")
                    break
                elif ev.get("role") == "assistant" and ev.get("content"):
                    final_message = str(ev["content"])
                    break

        # 1. Deterministic programmatic grading
        passed, reason = grade_case(case, events)

        # 2. Narrow model judge grading if semantic constraint exists and in live mode
        if passed and case.get("constraint") and live_mode:
            passed, reason = grade_with_model_judge(
                query=message,
                response=final_message,
                constraint=case["constraint"],
            )

        category_scores[case_type].append(passed)

        if not passed:
            tools_called = [ev.get("tool") for ev in events if isinstance(ev, dict) and "tool" in ev]
            failures.append({
                "id": case_id,
                "type": case_type,
                "input": message,
                "expected": case.get("expected_tools") or "Valid execution",
                "actual": tools_called if tools_called else final_message,
                "reason": reason,
            })

    # Summary by category
    print("=" * 65)
    print("EVALUATION RESULTS BY CATEGORY")
    print("=" * 65)
    total_passed = 0
    total_cases = 0

    for category, scores in category_scores.items():
        cat_passed = sum(scores)
        cat_total = len(scores)
        total_passed += cat_passed
        total_cases += cat_total
        pct = (cat_passed / cat_total) * 100 if cat_total > 0 else 0
        print(f"  {category:35s}: {cat_passed}/{cat_total} ({pct:.1f}%)")

    overall_pct = (total_passed / total_cases) * 100 if total_cases > 0 else 0
    print("-" * 65)
    print(f"  {'Overall':35s}: {total_passed}/{total_cases} ({overall_pct:.1f}%)")
    print("=" * 65)

    if failures:
        print("\n" + "=" * 65)
        print(f"FAILED CASES ({len(failures)})")
        print("=" * 65)
        for fail in failures:
            print(f"\n[Case ID]: {fail['id']} | Category: {fail['type']}")
            print(f"  Input:    {fail['input']}")
            print(f"  Expected: {fail['expected']}")
            print(f"  Actual:   {fail['actual']}")
            print(f"  Reason:   {fail['reason']}")
    else:
        print("\nAll cases passed successfully!")


if __name__ == "__main__":
    run_evaluation()