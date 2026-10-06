# Merik Support Agent

A customer-support agent built on the Anthropic Messages API.

## Evaluation

To run the evaluation suite in one command:

```bash
python -m evaluation.run_eval
```

## Running with Pytest

```bash
pytest tests/test_eval_suite.py
```

## Setup

```bash
pip install -r requirements.txt
```

## Overview
- Evaluates 24 benchmark cases: 20 real customer interaction scenarios and 4 permanent red-team failure fixtures.
- Uses deterministic programmatic checks and narrow categorical model judging.
- Reports scores broken down by case type/category and logs failures with input, expected result, and actual output.