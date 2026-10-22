from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class Intent(StrEnum):
    BOOK = "book"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"
    STATUS = "status_query"
    ACCEPT = "accept_offer"
    DECLINE = "decline_offer"
    ANSWER = "clarification_answer"
    CHAT = "chat"


Subject = Literal["day", "date", "time_window", "week", "doctor", "booking_ref", "clinic"]


class ClaimDraft(BaseModel):
    kind: Literal["preference", "constraint", "intent"] = "preference"
    subject: Subject
    value: str
    polarity: Literal["positive", "negative"] = "positive"
    raw_span: str
    booking_hint: str | None = None


class Extraction(BaseModel):
    intent: Intent = Intent.CHAT
    claims: list[ClaimDraft] = Field(default_factory=list)
    offer_choice: int | None = None


class ToolCall(BaseModel):
    id: str = ""
    name: str
    args: dict = Field(default_factory=dict)


class AssistantStep(BaseModel):
    tool_calls: list[ToolCall] = Field(default_factory=list)
    text: str = ""


class PlanMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None


class ExtractRequest(BaseModel):
    turn_key: str
    text: str
    lang: str
    context: str


class PlanRequest(BaseModel):
    turn_key: str
    system: str
    messages: list[PlanMessage]
    tools: list[dict]
    allow_tools: bool = True


class SummaryRequest(BaseModel):
    structured: dict
    lang: str
    strict: bool = False


class LLMProvider(Protocol):
    async def extract(self, request: ExtractRequest) -> Extraction: ...

    async def step(self, request: PlanRequest) -> AssistantStep: ...

    async def summarize(self, request: SummaryRequest) -> str: ...
