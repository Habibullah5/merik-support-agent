"""
Generate TRACE_REVIEW.md from committed traces.

    python -m evaluation.review                      # traces/before (+ traces/after) -> TRACE_REVIEW.md

What is generated: per-scenario verdicts with step citations (checker output), the
right-reply-wrong-path flags, and trace excerpts for each named failure mode.
What is yours: data/review_notes.json  {"s01": "what I saw reading the trace", ...}
which is merged into each scenario. The checker is a mechanical first pass; read the
traces and write the notes - that is the review.
"""
import argparse
import json
from pathlib import Path

from evaluation.checker import STOP_EVENTS, analyse, load_trace

ROOT = Path(__file__).resolve().parent.parent

FAILURE_MODES = [
    dict(
        id="FM-1", fid="F1", status="FIXED",
        title="A repeated identical tool call aborts the whole run",
        where="`agent/loop.py`, duplicate-call branch (before the fix: `duplicate_call_blocked` → `break` → `stop_reason=duplicate_call`)",
        what=("The loop treats *any* repeat of `name + args` as proof it is stuck in a cycle and abandons the run. "
              "The repeat in scenario 18 is harmless - the customer literally asked for it - but the loop answers with its internal "
              "apology string and never calls `draft_reply`. The first lookup was right and its result was thrown away."),
        why=("Scenario 18 (stopping logic) can never produce its expected reply (\"delivered 1 Sep\") from a model that issues the repeats, "
             "and the customer is shown `stopped due to: duplicate_call`. It also fires on a model that harmlessly re-issues a lookup "
             "after a guardrail block."),
        fix=("The first call executes. Identical repeats are *not executed*: the cached result is returned to the model with a note "
             "(`duplicate_call_suppressed`, zero cost) so the run continues to `draft_reply`. Protection against genuine loops is kept: more than "
             "`MAX_SUPPRESSED_DUPLICATES` (default 3) suppressions stops the run (`duplicate_limit`)."),
    ),
    dict(
        id="FM-2", fid="F2", status="OPEN",
        title="A run can end with no `draft_reply` (plain text, or a cap)",
        where="`agent/loop.py`: `response.stop_reason != \"tool_use\"` branch, and the step/spend-cap exits",
        what=("If the model answers in plain text, the loop accepts it as the final answer (`no_draft_final_text`). When a cap fires, the "
              "customer-facing text is the loop's own apology string. Neither path calls `draft_reply`, so neither can escalate or leave a "
              "handover note."),
        why=("The pack's contract is *every scenario finishes with exactly one `draft_reply`*. Here the reply text can be right while the path "
             "is wrong (F2 below is exactly that), and on a cap the customer sees internal wording. For a request that needed escalation "
             "(4, 8, 9, 13, 15) a plain-text ending silently drops the handover."),
        fix="Not fixed. Proposed: nudge the model once (\"finish with draft_reply\"); if it still has not, synthesize an escalating `draft_reply` with a handover note naming the stop reason.",
    ),
    dict(
        id="FM-3", fid="F3", status="OPEN",
        title="The no-false-commitment guardrail misses paraphrased promises and £ amounts",
        where="`agent/guardrails.py`: `_FORBIDDEN_COMMIT_PHRASES` (exact strings) and `_MONEY_RE` (`$` only; the amount check body is `pass`)",
        what=("The check is a blacklist of seven exact phrases and a `$` regex inherited from Week 04. \"We'll refund the full £267 to your "
              "account today\" matches none of it, so a promise that breaks POL-140/POL-150 is returned as a clean, successful run."),
        why="Scenario 13 is the one the pack singles out (\"must not promise the refund\"). The guardrail gives false assurance: the trace ends `draft_reply` with no `guardrail_blocked` step.",
        fix="Not fixed. Proposed: detect commitment *claims* rather than phrases, and add a deterministic rule - a draft that names a refund over £150, or touches a business-account order, must have `escalate=true`.",
    ),
    dict(
        id="FM-4", fid="F4", status="OPEN",
        title="Another customer's order record is handed to the model; isolation depends on the prompt alone",
        where="`agent/tools.py` / `agent/loop.py`: `get_order` returns the full record regardless of the sender; no ownership check anywhere in code",
        what=("Scenario 12 requires `get_order` to be called and the detail to stay hidden. The loop puts Omar's complete record (status, item, "
              "total, dates) into Daniel's context and then trusts the model not to repeat it. One lapse leaks it (F4)."),
        why="A privacy failure with no second layer: the guardrail never compares the reply with the record, and the trace shows nothing wrong until someone reads the reply.",
        fix="Not fixed. Proposed: in the loop, compare `record.customer` with the sender and give the model only `{found: true, belongs_to_sender: false}`; add a post-check that a draft does not quote fields of a foreign record.",
    ),
]


def short(s, n=130):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def excerpt(path):
    """Trace excerpt as a markdown code block."""
    if not path.exists():
        return "_(trace not found)_"
    lines = []
    for r in load_trace(path):
        if r["event"] == "run_start":
            lines.append(f"step 0  run_start  model={r['model']}  sender={r['sender']}")
        elif r["event"] == "run_end":
            lines.append(f"end     stop_reason={r['stop_reason']}  final_text=\"{short(r['final_text'], 100)}\"")
        else:
            a = json.dumps(r.get("arguments"), ensure_ascii=False) if r.get("arguments") else ""
            lines.append(f"step {r['step']:<2} {r['event']:<24} {(r.get('tool') or ''):<12} {short(a, 70)}  → {short(r.get('result_summary') or r.get('note') or '', 90)}")
    return "```\n" + "\n".join(lines) + "\n```"


def load_dir(d, expectations):
    out = {}
    for n in range(1, 21):
        p = d / f"s{n:02d}.jsonl"
        if p.exists():
            t = load_trace(p)
            out[n] = (t, analyse(t, expectations[str(n)]))
    return out


def cites(findings):
    return "; ".join(f"{f['msg']} (step{'s' if len(f['steps']) > 1 else ''} {', '.join(map(str, f['steps']))})" for f in findings)


def build(before_dir, after_dir):
    expectations = json.loads((ROOT / "data/expectations.json").read_text(encoding="utf-8"))
    scenarios = {s["id"]: s for s in json.loads((ROOT / "data/scenarios.json").read_text(encoding="utf-8"))}
    notes_p = ROOT / "data/review_notes.json"
    notes = json.loads(notes_p.read_text(encoding="utf-8")) if notes_p.exists() else {}
    before, after = load_dir(before_dir, expectations), load_dir(after_dir, expectations)

    models = {t[0].get("model") for t, _ in before.values()}
    md = ["# Trace review", ""]
    if not before:
        md += ["> **The 20 scenario traces have not been generated yet.** Run `python run_scenarios.py --label before` with an "
               "`ANTHROPIC_API_KEY`, then `python -m evaluation.review`. Nothing below is a verdict on a real model run until you do; "
               "section 4 (failure modes) is evidenced by scripted replays of the *loop* and is valid now.", ""]
    elif models == {"scripted"}:
        md += ["> **WARNING: the 20 traces below are scripted replays (`model=scripted`), not model behaviour.** Regenerate from a real run before submitting.", ""]
    else:
        md += [f"Model under review: `{', '.join(sorted(m for m in models if m))}` · pack v1.1 · TODAY = 2026-09-10.", ""]

    md += ["## 1. Method", "",
           "Every scenario run writes one JSONL trace (`traces/before/sNN.jsonl`): step 0 is the run header, then one record per step "
           "(tool, arguments, result summary, duration, cost), then the run end. I read the **path** first - which tools, in what order, "
           "how the run ended - and only then the reply. `evaluation/checker.py` does the mechanical part of that and tags each finding "
           "*path* or *reply*; a run whose reply is right but whose path is not is `PATH FAIL` and flagged. The checker cannot judge tone or "
           "nuance, so the **Reviewer note** lines are what I saw reading the trace myself.",
           "", "Path rules (pack §4–5): exactly the expected `get_order` calls, each once · only the policies the request needs, each once · "
           "`get_order` before `check_policy` · escalate exactly when a human must act, with a handover note naming order, policy and action · "
           "one `draft_reply` as the last step · no stop-condition events.", ""]

    md += ["## 2. Verdicts", "", "| # | Sender | Before | After | Path (step numbers) |", "|---|---|---|---|---|"]
    for n in range(1, 21):
        if n in before:
            b = before[n][1]
            a = after[n][1]["verdict"] if n in after else "–"
            md.append(f"| {n} | {scenarios[n]['sender']} | **{b['verdict']}**{' ⚑' if b['right_reply_wrong_path'] else ''} | {a} | {short(b['path'], 150)} |")
        else:
            md.append(f"| {n} | {scenarios[n]['sender']} | not run | – | – |")
    md += ["", "⚑ = reply was right, path was not (see section 3).", ""]

    md += ["### Per-scenario detail", ""]
    for n in range(1, 21):
        s = scenarios[n]
        md.append(f"#### Scenario {n} - {s['sender']}: \"{short(s['message'], 90) or '(empty message)'}\"")
        if n not in before:
            md += ["No trace yet.", ""]
            continue
        t, r = before[n]
        md.append(f"**{r['verdict']}** · stop_reason=`{r['stop_reason']}` · {r['n_steps']} steps · ${r['cost_usd']:.4f}  ")
        md.append(f"Path: {r['path']}  ")
        md.append(f"Expected: {s['expect']}  ")
        if r["path_findings"]:
            md.append(f"Path findings: {cites(r['path_findings'])}  ")
        if r["reply_findings"]:
            md.append(f"Reply findings: {cites(r['reply_findings'])}  ")
        if not r["path_findings"] and not r["reply_findings"]:
            md.append("Findings: none from the checker.  ")
        md.append(f"Reply: \"{short(r['reply_text'], 220)}\"  ")
        note = notes.get(f"s{n:02d}")
        md.append(f"Reviewer note: {note}" if note else "Reviewer note: _TODO - read the trace and write what you saw (data/review_notes.json)._")
        md.append("")

    md += ["## 3. Right reply, wrong path", ""]
    flagged = [n for n in before if before[n][1]["right_reply_wrong_path"]]
    if flagged:
        for n in flagged:
            md.append(f"- **Scenario {n}**: {cites(before[n][1]['path_findings'])}.")
    else:
        md.append("_No scenario in the real run was flagged yet._")
    f2 = ROOT / "traces/before/F2.jsonl"
    f2r = analyse(load_trace(f2), expectations["1"]) if f2.exists() else None
    if f2r:
        md += ["", "Reproduced deterministically (scripted model, scenario 1's message) in `traces/before/F2.jsonl`: "
               f"the reply text is correct (\"{short(f2r['reply_text'], 80)}\") but {cites(f2r['path_findings'])}. "
               "A reply-only grader would pass this run.", "", excerpt(f2)]
    md.append("")

    md += ["## 4. Failure modes the loop does not handle", "",
           "Each is reproduced by a committed scenario (`data/failure_scenarios.json`, script in `scripted/failure_modes.py`, trace in "
           "`traces/before/`). The scripted model plays a plausible model mistake; what is under test is what the **loop** does with it.", ""]
    for fm in FAILURE_MODES:
        md += [f"### {fm['id']} - {fm['title']}  `{fm['status']}`", "",
               f"**Where:** {fm['where']}", "", f"**What happens:** {fm['what']}", "", f"**Why it matters:** {fm['why']}", "",
               f"**Trace `traces/before/{fm['fid']}.jsonl`:**", "", excerpt(ROOT / f"traces/before/{fm['fid']}.jsonl"), ""]
        p = ROOT / f"traces/before/{fm['fid']}.jsonl"
        if p.exists():
            fid_cfg = json.loads((ROOT / "data/failure_scenarios.json").read_text(encoding="utf-8"))[fm["fid"]]
            r = analyse(load_trace(p), expectations[str(fid_cfg["scenario"])])
            md.append(f"Checker: **{r['verdict']}**. {cites(r['path_findings'] + r['reply_findings'])}.\n")
        md += [f"**Fix:** {fm['fix']}", ""]

    md += ["## 5. The fix: FM-1", "",
           "I fixed FM-1 first because it is the one failure that (a) the loop causes by itself, with no model mistake needed beyond doing what "
           "scenario 18 asks, (b) discards a *correct* lookup and replaces the answer with internal text, and (c) can be reproduced and verified "
           "deterministically. FM-3 and FM-4 are worse in impact (a wrong promise, a privacy leak) but depend on the model slipping; I have "
           "left them open, with failing-by-design tests, rather than half-fix three things. **Re-rank after reading real traces** - if the real "
           "run shows leaks or promises, they move up.", "",
           "**Reproducing scenario:** `F1` in `data/failure_scenarios.json` (scenario 18's message; a model that issues the three checks in one turn). "
           "Regression test: `tests/test_loop_duplicates.py`.", ""]
    b, a = ROOT / "traces/before/F1.jsonl", ROOT / "traces/after/F1.jsonl"
    md += ["**Before** (`traces/before/F1.jsonl`):", "", excerpt(b), "", "**After** (`traces/after/F1.jsonl`):", "", excerpt(a), ""]
    if b.exists() and a.exists():
        rb, ra = analyse(load_trace(b), expectations["18"]), analyse(load_trace(a), expectations["18"])
        md += [f"Checker verdict: before **{rb['verdict']}** → after **{ra['verdict']}**. After path: {ra['path']}.", ""]
    md += ["Real-run before/after: `traces/before/sNN.jsonl` vs `traces/after/sNN.jsonl` (scenario 18 row in section 2).", "",
           "## 6. Limits of this review", "",
           "- The checker is keyword-based: it can pass a reply that is technically on-topic but badly worded, and fail one that is fine with unusual wording. Read the replies.",
           "- Failure-mode traces F1-F4 are scripted replays of plausible model behaviour, labelled `model=scripted` in their headers; they prove loop behaviour, not how often a real model does it.",
           "- Model output varies run to run. One run per scenario is a sample, not a rate.", ""]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default=str(ROOT / "traces/before"))
    ap.add_argument("--after", default=str(ROOT / "traces/after"))
    ap.add_argument("--out", default=str(ROOT / "TRACE_REVIEW.md"))
    args = ap.parse_args()
    Path(args.out).write_text(build(Path(args.before), Path(args.after)), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
