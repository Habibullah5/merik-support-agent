import json
import os
from datetime import datetime, timezone

from agent.config import TODAY_ISO
from agent.guardrails import GuardrailViolation, check_post_call, check_pre_call
from agent.logging_utils import StepLogger, Timer
from agent.pricing import estimate_cost_usd
from agent.prompt import SYSTEM_PROMPT, format_user_message
from agent.tools import TOOL_FUNCTIONS, TOOLS_SCHEMA


def _call_key(name: str, args: dict) -> str:
    return name + "::" + json.dumps(args, sort_keys=True)


def _tool_result(call_id, payload, is_error=False):
    block = {"type": "tool_result", "tool_use_id": call_id, "content": json.dumps(payload, ensure_ascii=False)}
    if is_error:
        block["is_error"] = True
    return block


def run_agent(
    message: str,
    sender: str,
    *,
    client=None,
    scenario=None,
    max_steps: int = None,
    max_spend_usd: float = None,
    model: str = None,
    log_path: str = None,
    verbose: bool = True,
) -> dict:
    """Run one support message through the agent. Returns a dict with the final
    reply, why the run stopped, cost, and the trace path.

    Stop conditions: draft_reply succeeded | step cap | spend cap | duplicate call
    | model produced plain text instead of draft_reply.
    """
    max_steps = int(os.environ.get("MAX_STEPS", 8)) if max_steps is None else max_steps
    max_spend_usd = float(os.environ.get("MAX_SPEND_USD", 0.50)) if max_spend_usd is None else max_spend_usd
    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    max_suppressed = int(os.environ.get("MAX_SUPPRESSED_DUPLICATES", 3))

    if client is None:
        import anthropic  # imported lazily so offline tests need no SDK
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        model_label = model
    else:
        model_label = "scripted" if type(client).__name__ == "ScriptedClient" else model

    if log_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log_path = os.path.join("logs", f"run_{ts}.jsonl")
    logger = StepLogger(log_path, scenario=scenario, verbose=verbose)
    logger.header(model=model_label, sender=sender, message=message, today=TODAY_ISO,
                  max_steps=max_steps, max_spend_usd=max_spend_usd)

    messages = [{"role": "user", "content": format_user_message(sender, message)}]
    seen_calls = set()
    call_cache = {}  # key -> what the model was shown the first time (FM-1 fix)
    suppressed = 0
    cumulative_cost = 0.0
    draft = None
    final_text = None
    stop_reason = "unknown"

    for _turn in range(max_steps):
        with Timer() as t:
            response = client.messages.create(
                model=model, max_tokens=1024, system=SYSTEM_PROMPT,
                tools=TOOLS_SCHEMA, messages=messages,
            )
        usage = response.usage
        turn_cost = estimate_cost_usd(usage.input_tokens, usage.output_tokens)
        cumulative_cost += turn_cost
        # cost/time of this model turn is attributed to the first record the turn produces
        pending = {"ms": t.elapsed_ms, "cost": turn_cost}

        def attrib():
            out = dict(duration_ms=pending["ms"], cost_usd=pending["cost"])
            pending["ms"] = pending["cost"] = 0.0
            return out

        if cumulative_cost > max_spend_usd:
            stop_reason = "spend_cap"
            logger.log("stop_spend_cap", cumulative_cost_usd=cumulative_cost, **attrib(),
                       note=f"cumulative ${cumulative_cost:.5f} exceeds cap ${max_spend_usd:.5f}")
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # The model answered in plain text instead of calling draft_reply.
            final_text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            stop_reason = "final_answer"
            logger.log("no_draft_final_text", result=None, cumulative_cost_usd=cumulative_cost, **attrib(),
                       note="model ended its turn with plain text, no draft_reply call")
            break

        tool_results = []
        duplicate_hit = False

        for block in response.content:
            if block.type != "tool_use":
                continue
            name, args, call_id = block.name, block.input, block.id
            key = _call_key(name, args)

            if key in seen_calls:
                # FM-1 fix: an identical repeat is not a reason to abandon the run. Do NOT execute it
                # again; hand the model the earlier result and let it carry on to draft_reply.
                # Only a model that keeps repeating (> max_suppressed) is treated as stuck.
                suppressed += 1
                earlier = call_cache.get(key, {"error": "earlier identical call produced no result"})
                logger.log("duplicate_call_suppressed", tool=name, arguments=args, result=earlier,
                           cumulative_cost_usd=cumulative_cost, **attrib(),
                           note=f"identical call already made; cached result returned, not re-executed ({suppressed}/{max_suppressed})")
                tool_results.append(_tool_result(call_id, {
                    "duplicate_call": True,
                    "note": "You already made this exact call. Result unchanged - do not repeat it; use it and continue to draft_reply.",
                    "earlier_result": earlier,
                }))
                if suppressed > max_suppressed:
                    duplicate_hit = True
                    break
                continue
            seen_calls.add(key)

            # --- guardrail: pre-call ---
            try:
                check_pre_call(name, args)
            except GuardrailViolation as gv:
                logger.log("guardrail_blocked", tool=name, arguments=args,
                           result={"error": gv.detail, "rule": gv.rule},
                           cumulative_cost_usd=cumulative_cost, **attrib(), note="blocked before execution")
                call_cache[key] = {"error": f"blocked by guardrail: {gv.detail}"}
                tool_results.append(_tool_result(call_id, call_cache[key], True))
                continue

            # --- execute tool ---
            with Timer() as tt:
                try:
                    result = TOOL_FUNCTIONS[name](**args)
                    error = None
                except Exception as e:  # tool-level failure (bad arguments etc.)
                    result = {"error": f"tool_failed: {e}"}
                    error = str(e)

            # --- guardrail: post-call ---
            if error is None:
                try:
                    check_post_call(name, args, result)
                except GuardrailViolation as gv:
                    logger.log("guardrail_blocked", tool=name, arguments=args,
                               result={"error": gv.detail, "rule": gv.rule},
                               cumulative_cost_usd=cumulative_cost,
                               **{**attrib(), "duration_ms": tt.elapsed_ms},
                               note="blocked after execution, result discarded")
                    call_cache[key] = {"error": f"blocked by guardrail: {gv.detail}"}
                    tool_results.append(_tool_result(call_id, call_cache[key], True))
                    continue

            call_cache[key] = result
            a = attrib()
            a["duration_ms"] += tt.elapsed_ms
            logger.log("tool_call", tool=name, arguments=args, result=result,
                       cumulative_cost_usd=cumulative_cost, **a)
            tool_results.append(_tool_result(call_id, result, error is not None))

            if name == "draft_reply" and error is None:
                draft = result
                break

        if draft is not None:
            stop_reason = "draft_reply"
            final_text = draft["message"]
            break
        if duplicate_hit:
            stop_reason = "duplicate_limit"
            logger.log("stop_duplicate_limit", cumulative_cost_usd=cumulative_cost,
                       note=f"{suppressed} identical repeats suppressed (limit {max_suppressed}); model looks stuck")
            break

        messages.append({"role": "user", "content": tool_results})
    else:
        stop_reason = "step_cap"
        logger.log("stop_step_cap", cumulative_cost_usd=cumulative_cost, note=f"reached max_steps={max_steps}")

    if final_text is None:
        final_text = (
            "I wasn't able to finish drafting a reply within the allowed "
            f"steps/budget (stopped due to: {stop_reason}). "
            "Please try a more specific request, e.g. include the order id."
        )
    logger.end(stop_reason, final_text)

    return {
        "final_text": final_text,
        "draft": draft,
        "stop_reason": stop_reason,
        "cumulative_cost_usd": cumulative_cost,
        "log_path": logger.path,
    }
