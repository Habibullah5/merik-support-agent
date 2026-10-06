import json
from collections import defaultdict
from pathlib import Path

from agent.loop import run_agent
from evaluation.checker import grade_case
from evaluation.judge import grade_with_model_judge


def run_evaluation():
    base_dir = Path(__file__).resolve().parent.parent
    cases_file = base_dir / "data" / "eval_cases.json"

    if not cases_file.is_file():
        # Fallback to scenarios.json if eval_cases is empty
        cases_file = base_dir / "data" / "scenarios.json"

    with open(cases_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    category_scores = defaultdict(list)
    failures = []

    print(f"Running evaluation suite on {len(cases)} cases...\n")

    for idx, case in enumerate(cases, 1):
        case_id = case.get("id", f"case_{idx}")
        case_type = case.get("type", "general")
        message = case.get("message", case.get("query", ""))
        sender = case.get("customer") or case.get("sender", "customer")

        # Execute agent loop
        try:
            result = run_agent(
                message=message,
                sender=sender,
                scenario=case.get("scenario"),
            )
        except Exception as e:
            category_scores[case_type].append(False)
            failures.append({
                "id": case_id,
                "type": case_type,
                "input": message,
                "expected": case.get("expected", "Successful completion"),
                "actual": f"Crash: {e}",
                "reason": str(e),
            })
            continue

        # Extract events and final message
        events = result if isinstance(result, list) else result.get("events", [])
        final_message = ""
        if isinstance(result, dict):
            final_message = result.get("response", "")
        if not final_message and events:
            for ev in reversed(events):
                if ev.get("role") == "assistant" and ev.get("content"):
                    final_message = ev["content"]
                    break

        # Grade using cheapest method first (checker / programmatic)
        passed, reason = grade_case(case, events)

        # Fallback to model judge if programmatic passes but model check is needed
        if passed and case.get("constraint"):
            passed, reason = grade_with_model_judge(
                query=message,
                response=final_message,
                constraint=case["constraint"],
            )

        category_scores[case_type].append(passed)

        if not passed:
            failures.append({
                "id": case_id,
                "type": case_type,
                "input": message,
                "expected": case.get("expected_tools") or case.get("expected") or "Pass criteria",
                "actual": final_message or [e.get("tool_name") for e in events if "tool_name" in e],
                "reason": reason,
            })

    # Requirement: Output breaks the score down by case type, not one blended number
    print("=" * 60)
    print("EVALUATION RESULTS BY CATEGORY")
    print("=" * 60)
    total_passed = 0
    total_cases = 0

    for category, scores in category_scores.items():
        cat_passed = sum(scores)
        cat_total = len(scores)
        total_passed += cat_passed
        total_cases += cat_total
        pct = (cat_passed / cat_total) * 100 if cat_total > 0 else 0
        print(f"  {category:25s}: {cat_passed}/{cat_total} ({pct:.1f}%)")

    overall_pct = (total_passed / total_cases) * 100 if total_cases > 0 else 0
    print("-" * 60)
    print(f"  {'Overall':25s}: {total_passed}/{total_cases} ({overall_pct:.1f}%)")
    print("=" * 60)

    # Requirement: Failures are printed with the input, expected result and what came back
    if failures:
        print("\n" + "=" * 60)
        print(f"FAILED CASES ({len(failures)})")
        print("=" * 60)
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