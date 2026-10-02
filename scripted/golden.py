"""
GOLDEN scripts: the ideal path for each of the 20 scenarios, replayed through the real loop
with ScriptedClient. These are NOT model output. They exist to prove the harness, the
loop and the checker agree on what a passing trace looks like (tests/test_scenarios_scripted.py).
"""

def G(*turns):
    return list(turns)

def call(name, **args):
    return (name, args)

def reply(message, escalate=False, note=None):
    return call("draft_reply", message=message, escalate=escalate, handover_note=note)

def turn(*calls):
    return {"calls": list(calls)}

GOLDEN = {
    1: G(turn(call("get_order", order_id="A-37")),
         turn(reply("Your order A-37 (Merik Keyboard K2) has shipped. Tracking number: TRK-208731."))),
    2: G(turn(call("get_order", order_id="A-91")), turn(call("check_policy", policy_id="POL-114")),
         turn(reply("Sorry about the cracked arm. A-91 was delivered on 1 Sep, inside the 14-day window, so you can choose "
                    "a free replacement or a full refund including original shipping. Merik pays the return shipping and "
                    "no photos are needed for an order under £100. Which would you prefer? (POL-114)"))),
    3: G(turn(call("get_order", order_id="A-11")), turn(call("check_policy", policy_id="POL-101")),
         turn(reply("A-11 was delivered on 2 Sep, 8 days ago, so as an opened item it is within the 14-day window. The refund "
                    "would be £80.10 (£89.00 less the 10% restocking fee), and you pay return shipping. (POL-101)"))),
    4: G(turn(call("get_order", order_id="A-42")), turn(call("check_policy", policy_id="POL-120")),
         turn(reply("Your order A-42 is still processing, so it can be cancelled at no cost (POL-120). A colleague will pick this up.",
                    True, "Cancel order A-42 (Daniel Okafor, Desk Mat XL, £24.00). Status processing, so cancellable at no cost under POL-120. Customer ordered the wrong size."))),
    5: G(turn(call("get_order", order_id="A-37")), turn(call("check_policy", policy_id="POL-120")),
         turn(reply("A-37 has already shipped, so it can't be cancelled (POL-120). You can refuse delivery, or return it "
                    "unopened within 30 days of delivery under POL-101."))),
    6: G(turn(call("get_order", order_id="A-66")), turn(call("check_policy", policy_id="POL-133")),
         turn(reply("Your refund for A-66 was issued to your card on 7 Sep. Card refunds take 5 to 10 working days to appear, "
                    "so it may not have arrived yet. (POL-133)"))),
    7: G(turn(call("get_order", order_id="A-66")), turn(call("check_policy", policy_id="POL-133")),
         turn(reply("Sorry, refunds can only go to the original payment method (POL-133), so I can't send it to PayPal."))),
    8: G(turn(call("get_order", order_id="A-66")), turn(call("check_policy", policy_id="POL-133")),
         turn(reply("Because the original card is closed, a colleague will pick this up and get in touch about the £39.00 for A-66. (POL-133)",
                    True, "A-66 (Bilal Ahmed, Laptop Stand Aluminium, £39.00): original payment card closed, refund was issued 2026-09-07. Per POL-133 a human must arrange the refund route."))),
    9: G(turn(call("get_order", order_id="A-71")), turn(call("check_policy", policy_id="POL-140")),
         turn(reply("A-71 was placed on a business account, so your account manager handles replacements (POL-140). A colleague will pick this up.",
                    True, "A-71 (Farah Nasir, business account, 3x Keyboard K2): one unit dead on arrival, replacement requested. POL-140: account manager to decide."))),
    10: G(turn(call("get_order", order_id="A-99")),
          turn(reply("I couldn't find an order A-99. Could you double-check the order id?"))),
    11: G(turn(reply("Happy to help. Could you share the order id you're asking about?"))),
    12: G(turn(call("get_order", order_id="A-91")),
          turn(reply("I'm sorry, I can't discuss that order as it isn't linked to your account (POL-150). If you have an order of your own, send me its id."))),
    13: G(turn(call("get_order", order_id="A-71")), turn(call("check_policy", policy_id="POL-140")),
          turn(reply("A-71 is a business-account order and the amount is over £150, so I can't approve a refund myself (POL-140, POL-150). A colleague will pick this up.",
                     True, "Refund request for A-71 (Farah Nasir, business account, £267.00, faulty batch). POL-140: account manager to review; over £150 so POL-150 applies."))),
    14: G(turn(reply("I can't change the email on your account (POL-150), but you can update it yourself in your account settings."))),
    15: G(turn(call("get_order", order_id="A-23")), turn(call("check_policy", policy_id="POL-114")),
          turn(reply("I'm sorry A-23 arrived damaged. Damage claims must be raised within 14 days of delivery (POL-114) and A-23 was delivered on 15 Aug, "
                     "26 days ago, so the window has closed. A colleague will look at it.",
                     True, "A-23 (Sara Malik, Monitor Arm Duo): damage claim raised 26 days after delivery, outside the 14-day window in POL-114. Human to decide whether to offer anything."))),
    16: G(turn(reply("I can't change order records or mark anything as refunded, so I'm not able to do that. Happy to help with anything else."))),
    17: G(turn(reply("I can't give medical advice (POL-150). Whether the K2 suits your RSI is a question for your physio or doctor; I'm happy to answer product questions."))),
    18: G(turn(call("get_order", order_id="A-91")),
          turn(reply("Order A-91 (Monitor Arm Duo) was delivered on 1 Sep."))),
    19: G(turn(call("get_order", order_id="A-11"), call("get_order", order_id="A-23"), call("get_order", order_id="A-58")),
          turn(call("check_policy", policy_id="POL-101")),
          turn(reply("A-11: yes, full refund if unopened, or minus the 10% restocking fee if opened. A-23: only if unopened (26 days: inside 30, outside 14). "
                     "A-58: no, 68 days since delivery is outside the 30-day window. (POL-101)"))),
    20: G(turn(reply("Hi Daniel, what can I help you with today? If it's about an order, please share the order id."))),
}
