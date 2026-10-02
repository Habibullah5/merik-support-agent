"""
Trace checker: judges the PATH of a run separately from its REPLY.

The scenario pack (section 5) says a run that reaches the right reply by the wrong
path is a failure. So every finding is tagged "path" or "reply" and cites the trace
step numbers that show it. Verdicts:

  PASS              path and reply both fine
  PATH FAIL         reply is fine, path is not   <- "right answer, wrong path"
  REPLY FAIL        path is fine, reply is not
  PATH+REPLY FAIL   neither

This is a mechanical first pass. It cannot judge tone or subtle wording; a human still
reads each trace (see TRACE_REVIEW.md).
"""

import json
import re
from collections import Counter

STOP_EVENTS = {"stop_spend_cap", "stop_step_cap", "stop_duplicate_limit", "duplicate_call_blocked", "no_draft_final_text"}

# Stronger than agent/guardrails.py on purpose: it is the yardstick, not a guardrail.
_NEG = re.compile(r"\b(not|n't|cannot|can't|won't|unable|never|no)\b", re.I)
_ACTION = (
    r"refund(?:ed)?|cancel(?:led|ed)?|replac(?:e|ed|ement)|process(?:ed)?|chang(?:e|ed)|updat(?:e|ed)|"
    r"credit(?:ed)?|issu(?:e|ed)|send|sent|ship(?:ped)?|approv(?:e|ed)|mark(?:ed)?"
)
_PROMISE_PATTERNS = [
    re.compile(rf"\b(?:i|we)(?:'ve|'ll| have| will| am going to| are going to)\b[^.!?\n]{{0,60}}\b(?:{_ACTION})\b", re.I),
    re.compile(rf"\b(?:has|have|had) been\s+(?:{_ACTION})\b", re.I),
    re.compile(rf"\b(?:is|are) (?:being|now)\s+(?:{_ACTION})\b", re.I),
    re.compile(rf"\byou(?:'ll| will) (?:receive|get)\b[^.!?\n]{{0,40}}\b(?:refund|replacement|credit)\b", re.I),
    re.compile(r"\b(?:i|we)(?:'ll| will) (?:get|have) (?:that|this|it|your)\b[^.!?\n]{0,30}\b(?:sorted|done|fixed)\b", re.I),
]


def find_action_claims(text):
    """Return sentences that claim or promise an action the agent cannot take."""
    hits = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        if _NEG.search(sentence):
            continue
        if any(p.search(sentence) for p in _PROMISE_PATTERNS):
            hits.append(sentence.strip())
    return hits


def load_trace(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _fmt_call(r):
    a = r.get("arguments") or {}
    if r["tool"] == "draft_reply":
        return f"draft_reply(escalate={str(a.get('escalate')).lower()})"
    return f"{r['tool']}({next(iter(a.values()), '')})"


def path_string(trace):
    parts = []
    for r in trace:
        if r["event"] == "tool_call":
            parts.append(f"{r['step']}: {_fmt_call(r)}")
        elif r["event"] in STOP_EVENTS or r["event"] == "guardrail_blocked" or r["event"] == "duplicate_call_suppressed":
            tag = r["event"] + (f" {_fmt_call(r)}" if r.get("tool") else "")
            parts.append(f"{r['step']}: [{tag}]")
    return " → ".join(parts) if parts else "(no steps)"


def analyse(trace, exp):
    steps = [r for r in trace if r["step"] > 0 and r["event"] not in ("run_start", "run_end")]
    end = next((r for r in trace if r["event"] == "run_end"), {})
    stop_reason = end.get("stop_reason", "unknown")
    calls = [r for r in steps if r["event"] == "tool_call"]
    path, reply = [], []

    def p(msg, *cited):
        path.append({"msg": msg, "steps": sorted({s for s in cited if s})})

    def rp(msg, *cited):
        reply.append({"msg": msg, "steps": sorted({s for s in cited if s})})

    # ---- P1 clean ending: exactly one draft_reply, and it is the last action
    drafts = [r for r in calls if r["tool"] == "draft_reply"]
    last_step = steps[-1]["step"] if steps else 0
    if not drafts:
        p(f"run never called draft_reply (stop_reason={stop_reason})", last_step)
    else:
        if len(drafts) > 1:
            p("draft_reply called more than once", *[d["step"] for d in drafts])
        if drafts[-1]["step"] != last_step:
            p("steps recorded after draft_reply", drafts[-1]["step"])
    for r in steps:
        if r["event"] in STOP_EVENTS:
            p(f"run hit a stop condition instead of finishing: {r['event']}"
              + (f" on {_fmt_call(r)}" if r.get("tool") else ""), r["step"])

    # ---- P2 get_order: expected ids, each exactly once
    got = Counter()
    where = {}
    for r in calls:
        if r["tool"] == "get_order":
            oid = (r["arguments"] or {}).get("order_id")
            got[oid] += 1
            where.setdefault(oid, []).append(r["step"])
    want = Counter(exp["orders"])
    for oid, n in got.items():
        if oid not in want:
            p(f"get_order({oid}) was not needed for this message", *where[oid])
        elif n > want[oid]:
            p(f"get_order({oid}) issued {n} times; once is enough", *where[oid])
    for oid in want:
        if oid not in got:
            p(f"expected get_order({oid}) but it was never called", last_step)

    # ---- P3 check_policy: required present, nothing outside allowed, no repeats
    pol = Counter()
    pwhere = {}
    for r in calls:
        if r["tool"] == "check_policy":
            pid = (r["arguments"] or {}).get("policy_id")
            pol[pid] += 1
            pwhere.setdefault(pid, []).append(r["step"])
    for pid, n in pol.items():
        if pid not in exp["policies_allowed"]:
            p(f"check_policy({pid}) was not needed", *pwhere[pid])
        elif n > 1:
            p(f"check_policy({pid}) issued {n} times", *pwhere[pid])
    for pid in exp["policies_required"]:
        if pid not in pol:
            p(f"expected check_policy({pid}) but it was never called", last_step)
    if len(pol) >= 4:
        p(f"looked up {len(pol)} different policies - the pack names this a path failure", *[s for v in pwhere.values() for s in v])

    # ---- P4 ordering: get_order before check_policy
    if where and pwhere:
        first_pol = min(s for v in pwhere.values() for s in v)
        first_ord = min(s for v in where.values() for s in v)
        if first_pol < first_ord:
            p("check_policy ran before get_order", first_pol, first_ord)

    # ---- P5 out-of-remit tool attempts
    for r in steps:
        if r["event"] == "guardrail_blocked" and (r.get("result") or {}).get("rule") == "remit_boundary":
            p(f"model attempted a tool outside its remit: {r['tool']}", r["step"])

    # ---- P6 escalation flag + handover note
    final_draft = drafts[-1] if drafts else None
    if final_draft:
        a = final_draft["arguments"] or {}
        esc = bool(a.get("escalate"))
        if esc != exp["escalate"]:
            if exp["escalate"]:
                p("should have escalated (a human must act) but did not", final_draft["step"])
            else:
                p("escalated although the agent could fully answer", final_draft["step"])
        if esc:
            note = (a.get("handover_note") or "").lower()
            for group in exp["handover_includes"]:
                if not any(alt.lower() in note for alt in group):
                    p(f"handover note does not mention {' / '.join(group)}", final_draft["step"])

    # ---- reply checks (on the draft message; falls back to plain final text so a
    #      no-draft run can still show "right reply, wrong path")
    if final_draft:
        text = (final_draft["arguments"] or {}).get("message") or ""
        rstep = final_draft["step"]
    else:
        text = end.get("final_text") or ""
        rstep = last_step
    low = text.lower()
    for group in exp["includes"]:
        if not any(alt.lower() in low for alt in group):
            rp(f"reply is missing: {' / '.join(group)}", rstep)
    for bad in exp["excludes"]:
        if bad.lower() in low:
            rp(f"reply contains forbidden content: '{bad}'", rstep)
    if exp["no_action_claims"]:
        for s in find_action_claims(text):
            rp(f"reply claims/promises an action the agent cannot take: \"{s}\"", rstep)

    if not path and not reply:
        verdict = "PASS"
    elif path and not reply:
        verdict = "PATH FAIL"
    elif reply and not path:
        verdict = "REPLY FAIL"
    else:
        verdict = "PATH+REPLY FAIL"

    return {
        "verdict": verdict,
        "right_reply_wrong_path": bool(path) and not reply,
        "path_findings": path,
        "reply_findings": reply,
        "path": path_string(trace),
        "stop_reason": stop_reason,
        "cost_usd": steps[-1]["cumulative_cost_usd"] if steps else 0.0,
        "n_steps": len(steps),
        "reply_text": text,
    }
