import json
import os
from pathlib import Path
import pytest

from evaluation.checker import grade_case, load_trace

BASE_DIR = Path(__file__).resolve().parent.parent


def get_eval_cases():
    cases_file = BASE_DIR / "data" / "eval_cases.json"
    if not cases_file.is_file():
        cases_file = BASE_DIR / "data" / "scenarios.json"
    with open(cases_file, "r", encoding="utf-8") as f:
        return json.load(f)


EVAL_CASES = get_eval_cases()


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c.get("id", "case"))
def test_evaluation_case(case):
    case_id = case.get("id")
    # Only make live API calls if explicitly flagged via RUN_LIVE environment variable
    run_live = os.getenv("RUN_LIVE") == "1"

    if run_live:
        from agent.loop import run_agent
        result = run_agent(
            message=case.get("message", case.get("query", "")),
            sender=case.get("customer") or case.get("sender", "customer"),
            scenario=case.get("scenario"),
        )
        events = result if isinstance(result, list) else result.get("events", [])
    else:
        trace_path = BASE_DIR / "traces" / "reference_golden" / f"{case_id}.jsonl"
        if not trace_path.is_file():
            short_id = case_id.split("_")[0]
            trace_path = BASE_DIR / "traces" / "after" / f"{short_id}.jsonl"
            if not trace_path.is_file():
                trace_path = BASE_DIR / "traces" / "before" / f"{short_id}.jsonl"

        assert trace_path.is_file(), f"Trace fixture missing for case {case_id}"
        events = load_trace(trace_path)

    passed, reason = grade_case(case, events)
    assert passed, f"Case {case_id} failed: {reason}"