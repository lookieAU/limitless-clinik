from agent.llm.types import AssistantStep, Extraction


class LossySummarizer:
    async def extract(self, request) -> Extraction:
        return Extraction()

    async def step(self, request) -> AssistantStep:
        return AssistantStep()

    async def summarize(self, request) -> str:
        return "Prefers Thursday."
