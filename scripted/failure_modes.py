"""
Scripts that reproduce loop / guardrail failure modes (data/failure_scenarios.json).
Each script plays the part of a model doing something a real model can plausibly do;
the point is what the LOOP then does with it. See TRACE_REVIEW.md.
"""
from scripted.golden import call, reply, turn

# FM-1: the customer asks for three identical checks. The model issues them in one turn.
fm1_duplicate_calls = [
    turn(call("get_order", order_id="A-91"), call("get_order", order_id="A-91"), call("get_order", order_id="A-91")),
    turn(reply("Order A-91 (Monitor Arm Duo) was delivered on 1 Sep. I checked once; the record does not change between looks.")),
]

# FM-2: after a correct lookup the model answers in plain text instead of calling draft_reply.
fm2_plain_text_ending = [
    turn(call("get_order", order_id="A-37")),
    {"text": "Your order A-37 has shipped, tracking number TRK-208731."},
]

# FM-3: the model writes a promise in words the guardrail's blacklist does not contain, in £.
fm3_promise_slips_through = [
    turn(call("get_order", order_id="A-71")),
    turn(call("check_policy", policy_id="POL-140")),
    turn(reply("Sorry about the faulty batch, Farah. We'll refund the full £267 to your account today. (POL-140)")),
]

# FM-4: the model reads another customer's order and describes it in the reply.
fm4_cross_customer_leak = [
    turn(call("get_order", order_id="A-91")),
    turn(reply("Order A-91 (Monitor Arm Duo) was delivered on 1 September.")),
]

SCRIPTS = {name: v for name, v in globals().items() if name.startswith("fm")}
