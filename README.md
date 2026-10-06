# Merik Support Agent

A small customer-support agent on the Anthropic Messages API (tool use). It can **look things up and
write a reply; it cannot act**. It never issues refunds, cancels orders or edits accounts - when
something needs doing it escalates to a human with a handover note. Every run leaves a step-by-step trace.

This repo is the Week 04 agent, rebuilt on the **Merik Scenario Pack v1.1** (`docs/merik-support-scenarios.md`)
and extended with the Week 05 evaluation suite: an evaluation runner, deterministic programmatic checkers, a binary model judge, and permanent trace fixtures.

## Running the Evaluation Suite

Run the evaluation suite in one command:

```bash
python -m evaluation.run_eval