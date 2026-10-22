import json
from typing import get_args

import httpx
from pydantic import ValidationError

from agent.llm.prompts import EXTRACT_SYSTEM, STRICT_SUFFIX, SUMMARY_SYSTEM
from agent.llm.types import AssistantStep, ClaimDraft, Extraction, ExtractRequest, Intent, PlanMessage, PlanRequest, SummaryRequest, ToolCall

BASE_URL = "https://openrouter.ai/api/v1"
MAX_TOKENS = 16000


def enum_of(field: str) -> list[str]:
    return list(get_args(ClaimDraft.model_fields[field].annotation))


def extraction_schema() -> dict:
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "subject", "value", "polarity", "raw_span", "booking_hint"],
        "properties": {
            "kind": {"type": "string", "enum": enum_of("kind")},
            "subject": {"type": "string", "enum": enum_of("subject")},
            "value": {"type": "string"},
            "polarity": {"type": "string", "enum": enum_of("polarity")},
            "raw_span": {"type": "string"},
            "booking_hint": {"type": ["string", "null"]},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent", "claims", "offer_choice"],
        "properties": {
            "intent": {"type": "string", "enum": [intent.value for intent in Intent]},
            "claims": {"type": "array", "items": claim},
            "offer_choice": {"type": ["integer", "null"]},
        },
    }


def tool_specs(tools: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools
    ]


def assistant_message(message: PlanMessage) -> dict:
    if message.raw:
        return message.raw[0]
    calls = [
        {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.args)}}
        for call in message.tool_calls
    ]
    return {"role": "assistant", "content": message.text or None, **({"tool_calls": calls} if calls else {})}


def to_chat_messages(system: str, messages: list[PlanMessage]) -> list[dict]:
    result = [{"role": "system", "content": system}]
    for message in messages:
        if message.role == "tool":
            result.append({"role": "tool", "tool_call_id": message.tool_call_id, "content": message.text})
        elif message.role == "assistant":
            result.append(assistant_message(message))
        else:
            result.append({"role": "user", "content": message.text})
    return result


def first_message(payload: dict) -> dict:
    choices = payload.get("choices") or []
    return choices[0]["message"] if choices else {}


class OpenRouterProvider:
    def __init__(self, api_key: str, model: str, effort: str = "medium", client: httpx.AsyncClient | None = None):
        self.model = model
        self.effort = effort
        self.client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=90.0)
        self.headers = {"Authorization": f"Bearer {api_key}", "X-Title": "Clinik by Limitless"}

    async def complete(self, body: dict) -> dict:
        response = await self.client.post("/chat/completions", json={"model": self.model, "max_tokens": MAX_TOKENS, **body}, headers=self.headers)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise httpx.HTTPError(str(payload["error"]))
        return payload

    async def extract(self, request: ExtractRequest) -> Extraction:
        payload = await self.complete(
            {
                "messages": [
                    {"role": "system", "content": f"{EXTRACT_SYSTEM}\n\nContext:\n{request.context}"},
                    {"role": "user", "content": request.text},
                ],
                "response_format": {"type": "json_schema", "json_schema": {"name": "extraction", "strict": True, "schema": extraction_schema()}},
                "reasoning": {"effort": "low"},
                "provider": {"require_parameters": True},
            }
        )
        try:
            return Extraction.model_validate_json(first_message(payload).get("content") or "{}")
        except ValidationError:
            return Extraction()

    async def step(self, request: PlanRequest) -> AssistantStep:
        payload = await self.complete(
            {
                "messages": to_chat_messages(request.system, request.messages),
                **({"tools": tool_specs(request.tools), "tool_choice": "auto" if request.allow_tools else "none"} if request.tools else {}),
                "reasoning": {"effort": self.effort},
            }
        )
        message = first_message(payload)
        calls = [
            ToolCall(id=call["id"], name=call["function"]["name"], args=json.loads(call["function"].get("arguments") or "{}"))
            for call in message.get("tool_calls") or []
        ]
        raw = [{key: value for key, value in message.items() if key in ("role", "content", "tool_calls", "reasoning_details")}]
        return AssistantStep(tool_calls=calls if request.allow_tools else [], text=(message.get("content") or "").strip(), raw=raw)

    async def summarize(self, request: SummaryRequest) -> str:
        lang = "Hindi (Devanagari)" if request.lang == "hi" else "English"
        system = SUMMARY_SYSTEM.format(lang=lang) + (STRICT_SUFFIX if request.strict else "")
        payload = await self.complete(
            {
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(request.structured, ensure_ascii=False)}],
                "reasoning": {"effort": "low"},
            }
        )
        return (first_message(payload).get("content") or "").strip()
