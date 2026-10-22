from agent.llm.anthropic_provider import AnthropicProvider
from agent.settings import AgentSettings


def test_default_model_is_haiku_without_server_fallback():
    assert AgentSettings.anthropic_model == "claude-haiku-5-5"
    assert AnthropicProvider("key", AgentSettings.anthropic_model).fallback_options() == {}
