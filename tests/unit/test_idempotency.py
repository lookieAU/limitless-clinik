from shared.ids import idempotency_key


def test_key_is_stable_for_same_intent():
    assert idempotency_key("u", "book", "slot", "i1") == idempotency_key("u", "book", "slot", "i1")


def test_key_changes_for_new_intent_or_target():
    base = idempotency_key("u", "book", "slot", "i1")
    assert base != idempotency_key("u", "book", "slot", "i2")
    assert base != idempotency_key("u", "book", "other", "i1")
    assert base != idempotency_key("u", "cancel", "slot", "i1")


def test_default_model_is_haiku_without_server_fallback():
    from agent.llm.anthropic_provider import AnthropicProvider
    from agent.settings import AgentSettings

    assert AgentSettings.anthropic_model == "claude-haiku-5-5"
    assert AnthropicProvider("key", AgentSettings.anthropic_model).fallback_options() == {}
