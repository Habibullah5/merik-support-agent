from agent.tools import check_policy, draft_reply, get_order


def test_get_order_returns_pack_record():
    o = get_order("A-91")
    assert o["customer"] == "Omar Rashid" and o["status"] == "delivered" and o["total"] == "£64.50"


def test_get_order_not_found_for_unknown_and_malformed_ids():
    for bad in ("A-99", "A-9", "A-123", "a-91", "91", "", "A-91; DROP", None):
        assert get_order(bad) == {"error": "not_found"}


def test_get_order_does_not_search_by_name():
    assert get_order("Hina Qureshi") == {"error": "not_found"}


def test_all_eight_orders_and_six_policies_load():
    assert all("error" not in get_order(i) for i in ["A-11", "A-23", "A-37", "A-42", "A-58", "A-66", "A-71", "A-91"])
    assert all("error" not in check_policy(f"POL-{n}") for n in (101, 114, 120, 133, 140, 150))


def test_check_policy_unknown():
    assert check_policy("POL-999") == {"error": "unknown_policy"}
    assert check_policy("refund") == {"error": "unknown_policy"}


def test_policy_text_matches_pack():
    assert "14 days of delivery" in check_policy("POL-114")["text"]
    assert "10% restocking fee" in check_policy("POL-101")["text"]


def test_draft_reply_shape():
    d = draft_reply("hello", True, "note")
    assert d == {"drafted": True, "message": "hello", "escalate": True, "handover_note": "note"}
