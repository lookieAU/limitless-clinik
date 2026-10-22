import json

import httpx

from agent.llm.openrouter_provider import OpenRouterProvider, extraction_schema
from agent.llm.types import ExtractRequest, PlanMessage, PlanRequest, ToolCall
from agent.tools.specs import TOOL_SPECS


def provider(responses: list[dict], seen: list[dict]) -> OpenRouterProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://openrouter.ai/api/v1")
    return OpenRouterProvider("key", "anthropic/claude-haiku-5.5", client=client)


def reply(message: dict) -> dict:
    return {"choices": [{"message": {"role": "assistant", **message}}]}


def test_schema_is_strict_and_tracks_types():
    schema = extraction_schema()
    claim = schema["properties"]["claims"]["items"]
    assert schema["additionalProperties"] is False and claim["additionalProperties"] is False
    assert set(claim["required"]) == set(claim["properties"])
    assert "status_query" in schema["properties"]["intent"]["enum"] and "week" in claim["properties"]["subject"]["enum"]


async def test_extract_parses_structured_output():
    seen = []
    content = json.dumps({"intent": "book", "offer_choice": None, "claims": [
        {"kind": "constraint", "subject": "day", "value": "thu", "polarity": "negative", "raw_span": "not Thursday", "booking_hint": None}]})
    result = await provider([reply({"content": content})], seen).extract(ExtractRequest(turn_key="t", text="not Thursday", lang="en", context=""))
    assert result.claims[0].polarity == "negative"
    assert seen[0]["response_format"]["json_schema"]["strict"] is True
    assert seen[0]["model"] == "anthropic/claude-haiku-5.5"


async def test_step_maps_tool_calls_both_ways():
    seen = []
    call = {"id": "c1", "type": "function", "function": {"name": "get_booking", "arguments": "{}"}}
    llm = provider([reply({"content": None, "tool_calls": [call]})], seen)
    request = PlanRequest(turn_key="t", system="sys", tools=TOOL_SPECS, messages=[
        PlanMessage(role="user", text="hi"),
        PlanMessage(role="assistant", tool_calls=[ToolCall(id="c0", name="recall", args={"query": "x"})]),
        PlanMessage(role="tool", tool_call_id="c0", text="{}"),
    ])
    step = await llm.step(request)
    assert step.tool_calls[0].name == "get_booking" and step.raw[0]["tool_calls"] == [call]
    sent = seen[0]["messages"]
    assert sent[0]["role"] == "system" and sent[2]["tool_calls"][0]["function"]["arguments"] == '{"query": "x"}'
    assert sent[3] == {"role": "tool", "tool_call_id": "c0", "content": "{}"}
    assert seen[0]["tools"][0]["type"] == "function" and seen[0]["tool_choice"] == "auto"
