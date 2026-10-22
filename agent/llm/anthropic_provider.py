import json

import anthropic

from agent.llm.prompts import EXTRACT_SYSTEM, STRICT_SUFFIX, SUMMARY_SYSTEM
from agent.llm.types import AssistantStep, Extraction, ExtractRequest, PlanMessage, PlanRequest, SummaryRequest, ToolCall

FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
MAX_TOKENS = 16000


def assistant_content(message: PlanMessage) -> list | str:
    if message.raw is not None:
        return message.raw
    blocks = [{"type": "text", "text": message.text}] if message.text else []
    blocks += [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.args} for call in message.tool_calls]
    return blocks or message.text


def to_api_messages(messages: list[PlanMessage]) -> list[dict]:
    result: list[dict] = []
    for message in messages:
        if message.role == "tool":
            block = {"type": "tool_result", "tool_use_id": message.tool_call_id, "content": message.text}
            if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                result[-1]["content"].append(block)
            else:
                result.append({"role": "user", "content": [block]})
        elif message.role == "assistant":
            result.append({"role": "assistant", "content": assistant_content(message)})
        else:
            result.append({"role": "user", "content": message.text})
    return result


class AnthropicProvider:
    def __init__(self, api_key: str, model: str, effort: str = "medium"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=60.0)
        self.model = model
        self.effort = effort

    def fallback_options(self) -> dict:
        if self.model in FALLBACK_MODELS:
            return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return {}

    async def extract(self, request: ExtractRequest) -> Extraction:
        response = await self.client.beta.messages.parse(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=f"{EXTRACT_SYSTEM}\n\nContext:\n{request.context}",
            messages=[{"role": "user", "content": request.text}],
            output_format=Extraction,
            output_config={"effort": "low"},
            **self.fallback_options(),
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return Extraction()
        return response.parsed_output

    async def step(self, request: PlanRequest) -> AssistantStep:
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=request.system,
            messages=to_api_messages(request.messages),
            tools=request.tools,
            tool_choice={"type": "auto"} if request.allow_tools else {"type": "none"},
            output_config={"effort": self.effort},
            **self.fallback_options(),
        )
        if response.stop_reason == "refusal":
            return AssistantStep()
        raw = [block.model_dump(mode="json", exclude_none=True) for block in response.content]
        text = " ".join(block.text for block in response.content if block.type == "text").strip()
        calls = [ToolCall(id=block.id, name=block.name, args=dict(block.input)) for block in response.content if block.type == "tool_use"]
        return AssistantStep(tool_calls=calls if request.allow_tools else [], text=text, raw=raw)

    async def summarize(self, request: SummaryRequest) -> str:
        lang = "Hindi (Devanagari)" if request.lang == "hi" else "English"
        system = SUMMARY_SYSTEM.format(lang=lang) + (STRICT_SUFFIX if request.strict else "")
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": json.dumps(request.structured, ensure_ascii=False)}],
            output_config={"effort": "low"},
            **self.fallback_options(),
        )
        if response.stop_reason == "refusal":
            return ""
        return " ".join(block.text for block in response.content if block.type == "text").strip()
