from agent.llm.types import AssistantStep, Extraction
from agent.vocab import value_label


class LossySummarizer:
    async def extract(self, request) -> Extraction:
        return Extraction()

    async def step(self, request) -> AssistantStep:
        return AssistantStep()

    async def summarize(self, request) -> str:
        values = [value_label(item["subject"], item["value"], "en") for item in request.structured.get("constraints", [])]
        return f"Prefers {', '.join(values)}." if values else "Prefers Thursday."
