# Merik Support Agent

A small customer-support agent on the Anthropic Messages API (tool use). It can **look things up and
write a reply; it cannot act**. It never issues refunds, cancels orders or edits accounts - when
something needs doing it escalates to a human with a handover note. Every run leaves a step-by-step trace.

This repo is the Week 04 agent, rebuilt on the **Merik Scenario Pack v1.1** (`docs/merik-support-scenarios.md`)
and extended with the Week 05 review work: a trace checker, a review generator, committed before/after traces,
and a fix for one named failure mode. **Start with [`TRACE_REVIEW.md`](TRACE_REVIEW.md).**

## Setup

```bash
git clone <this-repo-url> && cd support-agent
python3 -m venv venv && source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then paste your ANTHROPIC_API_KEY
```

## Run it

```bash
python main.py --sender "Hina Qureshi" --message "Where is order A-37?"
```

The sender name travels with every message; the agent only discusses orders whose `customer` matches it.
`TODAY` is fixed at Thursday 10 September 2026 (`agent/config.py`, injected into the system prompt).

## The review workflow (what the grader looks at)

```bash
git checkout baseline                                  # the code BEFORE the FM-1 fix
python run_scenarios.py --label before                 # 20 scenarios, REAL model -> traces/before/s01..s20.jsonl
git checkout main                                      # the code AFTER the fix
python run_scenarios.py --label after                  # -> traces/after/s01..s20.jsonl
python -m evaluation.review                            # regenerates TRACE_REVIEW.md from both folders
git add -A && git commit -m "Real-model before/after traces and review" && git push
```

(About $0.30-0.60 per full pass at default Sonnet pricing; the spend cap is per scenario.)

Then **read the traces** and write what you saw in `data/review_notes.json` (`{"s06": "..."}`) and re-run the
last command - the notes are merged into each scenario's entry.

No API key? The loop, checker and failure modes can all be exercised offline with scripted replays:

```bash
python run_scenarios.py --label reference_golden --scripted        # ideal path for all 20 (harness self-test)
python run_scenarios.py --label after --failures --scripted        # the F1..F4 failure-mode reproductions
pytest -q                                                          # 78 passed + 3 strict xfails (the open gaps), offline and free
```

> Scripted traces carry `model="scripted"` in their header and are **not** model behaviour. They test the
> loop, guardrails and checker deterministically.

## The three tools (`agent/tools.py`)

| Tool | Input | Returns |
|---|---|---|
| `get_order` | `order_id` (`A-` + 2 digits) | the order record, or `{"error":"not_found"}`; no search by name |
| `check_policy` | `policy_id` | the policy text, or `{"error":"unknown_policy"}` |
| `draft_reply` | `message`, `escalate`, `handover_note` | **ends the run** - every run ends with exactly one |

Fixtures are parsed from the pack by `scripts/build_fixtures.py` into `data/` (8 orders, 6 policies, 20 scenarios).

## The loop (`agent/loop.py`)

Stops on: `draft_reply` succeeded · step cap (`MAX_STEPS`) · spend cap (`MAX_SPEND_USD`) · repeated-call limit ·
(a model ending in plain text is accepted but flagged - see FM-2). Guardrails (`agent/guardrails.py`) block calls to
tools outside the remit before they run, and check each draft after it is written.

## Trace format (`traces/<label>/<run>.jsonl`)

Step 0 is a `run_start` header (model, sender, message, today). Then one record per step with `step`, `event`,
`tool`, `arguments`, `result_summary`, `result`, `duration_ms`, `cost_usd`, `cumulative_cost_usd`, `note`; the
cost and time of the model turn that produced a tool call sit on the first record of that turn. The last
record is `run_end` (`stop_reason`, `final_text`).

## How runs are judged (`evaluation/checker.py`)

Path and reply are judged separately. Verdicts: `PASS`, `PATH FAIL` (right reply, wrong path - flagged),
`REPLY FAIL`, `PATH+REPLY FAIL`. Expectations per scenario are in `data/expectations.json`. The checker is
mechanical; it is the first pass of the review, not a replacement for reading the trace.

## Status: failure modes (details and traces in TRACE_REVIEW.md)

| ID | Failure mode | Reproduction | Status |
|---|---|---|---|
| FM-1 | Repeated identical call aborts the whole run | `F1` (scenario 18) | **fixed** - `git diff baseline fixed -- agent/loop.py` |
| FM-2 | Run can end with no `draft_reply` | `F2` | open (strict-xfail test) |
| FM-3 | Guardrail misses paraphrased / £ promises | `F3` (scenario 13) | open (strict-xfail test) |
| FM-4 | Another customer's order record reaches the model | `F4` (scenario 12) | open (strict-xfail test) |

Git tags: `baseline` (before the fix) and `fixed` (after). `traces/before/` and `traces/after/` were produced by those two commits.

## Layout

```
main.py                  one message from the CLI
run_scenarios.py         run the 20 scenarios / failure reproductions, write traces
agent/                   loop, tools, prompt, guardrails, logging, scripted client
evaluation/              checker.py (path vs reply verdicts), review.py (TRACE_REVIEW generator)
scripted/                golden.py (ideal paths), failure_modes.py (F1..F4 scripts)
data/                    orders, policies, scenarios (from the pack), expectations, failure_scenarios
docs/                    the scenario pack
traces/before|after/     committed trace logs (F1..F4 scripted; s01..s20 from your real runs)
traces/reference_golden/ what a passing trace looks like
tests/                   offline test suite
TRACE_REVIEW.md          verdicts, failure modes, the fix
```
