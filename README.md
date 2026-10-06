# Merik Support Agent

A customer-support agent on the Anthropic Messages API (tool use). It can **look things up and
write a reply; it cannot act**. It never issues refunds, cancels orders, or edits accounts — when
something needs doing, it escalates to a human with a handover note. Every run leaves a step-by-step trace.

This repo includes the Week 05 evaluation suite: an automated test runner, deterministic programmatic checkers, a binary model judge, and permanent trace fixtures.

---

## Evaluation Suite (Week 05 Grader)

### Quick Start (Single-Command Run)
Run the full 24-case evaluation suite with a single command from the repository root:

```bash
python -m evaluation.run_eval