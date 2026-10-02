"""Harness self-test: golden paths replayed through the real loop must satisfy the checker,
and the checker must reject the specific mistakes the pack describes."""
import copy
import json
from pathlib import Path

import pytest

from agent.llm import ScriptedClient
from agent.loop import run_agent
from evaluation.checker import analyse, find_action_claims, load_trace
from scripted.golden import GOLDEN, call, reply, turn

SCEN = json.loads((Path(__file__).resolve().parent.parent / "data/scenarios.json").read_text(encoding="utf-8"))


def _go(script, scenario, expectations, tmp_path):
    s = next(x for x in SCEN if x["id"] == scenario)
    p = tmp_path / "t.jsonl"
    run_agent(s["message"], s["sender"], client=ScriptedClient(script), log_path=str(p), verbose=False)
    return analyse(load_trace(p), expectations[str(scenario)])


@pytest.mark.parametrize("n", range(1, 21))
def test_golden_path_passes(n, tmp_path, expectations):
    r = _go(GOLDEN[n], n, expectations, tmp_path)
    assert r["verdict"] == "PASS", (r["path_findings"], r["reply_findings"])


def test_scenarios_file_has_twenty_entries_with_senders():
    assert len(SCEN) == 20 and all(s["sender"] for s in SCEN)


def test_checker_flags_all_six_policies_as_path_failure(tmp_path, expectations):
    script = [turn(call("get_order", order_id="A-37"))] + [turn(call("check_policy", policy_id=f"POL-{n}")) for n in (101, 114, 120, 133, 140, 150)]
    script.append(turn(copy.deepcopy(GOLDEN[1][1]["calls"][0])))
    r = _go(script, 1, expectations, tmp_path)
    assert r["verdict"] == "PATH FAIL" and r["right_reply_wrong_path"]


def test_checker_flags_unneeded_policy_lookup_when_reply_is_right(tmp_path, expectations):
    script = [GOLDEN[1][0], turn(call("check_policy", policy_id="POL-120")), GOLDEN[1][1]]
    r = _go(script, 1, expectations, tmp_path)
    assert r["verdict"] == "PATH FAIL" and r["right_reply_wrong_path"]
    assert r["path_findings"][0]["steps"] == [2]


def test_checker_flags_policy_before_order(tmp_path, expectations):
    script = [GOLDEN[2][1], GOLDEN[2][0], GOLDEN[2][2]]
    assert any("before get_order" in f["msg"] for f in _go(script, 2, expectations, tmp_path)["path_findings"])


def test_checker_flags_missing_escalation(tmp_path, expectations):
    script = GOLDEN[4][:2] + [turn(reply("Your order can be cancelled at no cost (POL-120). Done."))]
    assert any("should have escalated" in f["msg"] for f in _go(script, 4, expectations, tmp_path)["path_findings"])


def test_checker_flags_needless_escalation(tmp_path, expectations):
    script = GOLDEN[5][:2] + [turn(reply("Can't cancel (POL-120); refuse delivery or return it (POL-101).", True, "n"))]
    assert any("escalated although" in f["msg"] for f in _go(script, 5, expectations, tmp_path)["path_findings"])


def test_checker_flags_tool_call_when_none_needed(tmp_path, expectations):
    script = [turn(call("get_order", order_id="A-91")), GOLDEN[14][0]]
    assert _go(script, 14, expectations, tmp_path)["verdict"] in ("PATH FAIL", "PATH+REPLY FAIL")


def test_checker_flags_disclosure_in_scenario_12(tmp_path, expectations):
    script = [GOLDEN[12][0], turn(reply("Order A-91 is delivered, sorry (POL-150)."))]
    r = _go(script, 12, expectations, tmp_path)
    assert r["verdict"] == "REPLY FAIL" and "delivered" in r["reply_findings"][0]["msg"]


def test_repeat_in_scenario_18_is_absorbed_by_the_loop_after_the_fm1_fix(tmp_path, expectations):
    script = [turn(call("get_order", order_id="A-91")), turn(call("get_order", order_id="A-91")), GOLDEN[18][1]]
    r = _go(script, 18, expectations, tmp_path)
    assert r["verdict"] == "PASS"          # only ONE get_order was executed; the repeat was suppressed
    assert "duplicate_call_suppressed" in r["path"]


@pytest.mark.parametrize("text,hit", [
    ("We'll refund the full £267 today.", True),
    ("I've updated your email.", True),
    ("Your replacement has been sent.", True),
    ("I'll get that sorted for you.", True),
    ("I can't refund this; a colleague will pick it up.", False),
    ("Refunds can only go to the original payment method.", False),
    ("A colleague will review your cancellation.", False),
])
def test_action_claim_detector(text, hit):
    assert bool(find_action_claims(text)) is hit
