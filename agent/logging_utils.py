"""
Trace logging. One JSON line per step in traces / logs files.

Record fields (the pack, section 5): step, tool, arguments, result summary,
duration_ms, cost - plus event, scenario, full result and a note.

step 0 is a `run_start` header (model, sender, message, today). The last record is
a `run_end` (stop_reason, final_text). Every step in between is one tool action or
one stop event; the cost/duration of the model turn that produced a tool call is
attributed to the first record of that turn.
"""

import json
import os
import time
from datetime import datetime, timezone


def summarize(tool, result):
    """Short human-readable result summary for the trace."""
    if not isinstance(result, dict):
        return str(result)[:120]
    if "error" in result:
        return f"error: {result['error']}"
    if tool == "get_order":
        return f"{result['id']}: {result['status']}, {result['customer']}, {result['total']}, {result['notes'] or '-'}"
    if tool == "check_policy":
        return f"{result['policy_id']} {result['title']}"
    if tool == "draft_reply":
        m = (result.get("message") or "").replace("\n", " ")
        return f"escalate={str(result.get('escalate')).lower()}; \"{m[:110]}{'...' if len(m) > 110 else ''}\""
    return json.dumps(result)[:120]


class StepLogger:
    def __init__(self, path, scenario=None, verbose=True):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.scenario = scenario
        self.verbose = verbose
        self._step = 0
        self._f = open(path, "w", encoding="utf-8")

    def _write(self, record):
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._f.flush()

    def header(self, **meta):
        self._write({
            "step": 0, "scenario": self.scenario, "event": "run_start",
            "timestamp": datetime.now(timezone.utc).isoformat(), **meta,
        })

    def log(self, event, tool=None, arguments=None, result=None, duration_ms=0.0,
            cost_usd=0.0, cumulative_cost_usd=0.0, note=None):
        self._step += 1
        record = {
            "step": self._step,
            "scenario": self.scenario,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "tool": tool,
            "arguments": arguments,
            "result_summary": summarize(tool, result) if result is not None else None,
            "result": result,
            "duration_ms": round(duration_ms, 2),
            "cost_usd": round(cost_usd, 6),
            "cumulative_cost_usd": round(cumulative_cost_usd, 6),
            "note": note,
        }
        self._write(record)
        if self.verbose:
            args = json.dumps(arguments, ensure_ascii=False)[:58] if arguments else ""
            print(f"  [step {self._step:>2}] {event:<26} {tool or '':<12} {args:<60} "
                  f"{record['duration_ms']:>8.1f}ms ${record['cost_usd']:.5f} {note or ''}")
        return record

    def end(self, stop_reason, final_text):
        self._write({
            "step": self._step + 1, "scenario": self.scenario, "event": "run_end",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stop_reason": stop_reason, "final_text": final_text,
        })
        self._f.close()


class Timer:
    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000
