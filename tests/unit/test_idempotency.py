from shared.ids import idempotency_key


def test_key_is_stable_for_same_intent():
    assert idempotency_key("u", "book", "slot", "i1") == idempotency_key("u", "book", "slot", "i1")


def test_key_changes_for_new_intent_or_target():
    base = idempotency_key("u", "book", "slot", "i1")
    assert base != idempotency_key("u", "book", "slot", "i2")
    assert base != idempotency_key("u", "book", "other", "i1")
    assert base != idempotency_key("u", "cancel", "slot", "i1")
