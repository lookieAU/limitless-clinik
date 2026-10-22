from agent.llm.types import AssistantStep, Extraction, ExtractRequest, PlanRequest


class Recorder:
    def __init__(self):
        self.requests: list[PlanRequest] = []

    async def extract(self, request: ExtractRequest) -> Extraction:
        return Extraction(intent="book", claims=[
            {"subject": "day", "value": "thu", "raw_span": "Thursday"},
            {"subject": "time_window", "value": "15:00", "raw_span": "3pm"},
        ]) if "Thursday" in request.text else Extraction()

    async def step(self, request: PlanRequest) -> AssistantStep:
        self.requests.append(request)
        if len(self.requests) == 1:
            return AssistantStep(tool_calls=[{"name": "check_availability", "args": {"doctor_id": "dr_a", "date_from": "2026-11-05", "time_from": "15:00", "time_to": "15:00"}}])
        if len(self.requests) == 2:
            return AssistantStep(tool_calls=[{"name": "book", "args": {"slot_id": "dr_a_20261105_1500"}}])
        return AssistantStep(text="Anything else?")

    async def summarize(self, request) -> str:
        return ""


async def test_history_labels_system_lines_apart_from_model_prose(make_harness):
    recorder = Recorder()
    harness = await make_harness(llm=recorder)
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.say("thanks")
    last = recorder.requests[-1].messages
    assert [m.role for m in last] == ["user", "assistant", "user"]
    assert last[1].text.startswith("[Shown by the system, not written by you: Done — Dr Arjun Mehta")
    assert last[1].text.endswith("Anything else?")
