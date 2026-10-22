from collections import defaultdict, deque

from agent.llm.types import AssistantStep, Extraction, ExtractRequest, PlanRequest, SummaryRequest
from agent.memory.render import render_summary


class ScriptedProvider:
    def __init__(self, script: dict | None = None, summaries: list[str] | None = None):
        self.entries: dict[str, deque] = defaultdict(deque)
        self.turn_steps: dict[str, deque] = {}
        self.summaries = deque(summaries or [])
        self.calls: list[tuple[str, str]] = []
        for text, entry in (script or {}).items():
            self.add(text, entry)

    def add(self, text: str, entry: dict | list[dict]) -> None:
        for item in entry if isinstance(entry, list) else [entry]:
            self.entries[self.normalize(text)].append(item)

    @staticmethod
    def normalize(text: str) -> str:
        return " ".join(text.lower().split())

    async def extract(self, request: ExtractRequest) -> Extraction:
        self.calls.append(("extract", request.text))
        queue = self.entries.get(self.normalize(request.text))
        entry = queue.popleft() if queue else {}
        self.turn_steps[request.turn_key] = deque(AssistantStep(**step) for step in entry.get("steps", []))
        return Extraction(**entry.get("extract", {}))

    async def step(self, request: PlanRequest) -> AssistantStep:
        self.calls.append(("step", request.turn_key))
        queue = self.turn_steps.get(request.turn_key)
        return queue.popleft() if queue else AssistantStep()

    async def summarize(self, request: SummaryRequest) -> str:
        self.calls.append(("summarize", request.lang))
        if self.summaries:
            return self.summaries.popleft()
        return render_summary(request.structured, request.lang)
