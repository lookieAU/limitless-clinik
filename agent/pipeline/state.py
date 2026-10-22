from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent.llm.types import Extraction
from agent.pipeline.injection import InjectionScan
from agent.repo.audit import log_event
from shared.types import Slot

ORDER = ("notice", "uncertain", "question", "action", "status", "refusal", "offer", "info", "prose", "fallback")
BOOKING_KINDS = ("notice", "action", "status")


@dataclass
class Segment:
    kind: str
    key: str
    params: dict = field(default_factory=dict)
    booking_id: str | None = None


@dataclass
class TurnState:
    ctx: Any
    user: dict
    session: dict
    message_id: str
    text: str
    lang: str
    now: datetime
    extraction: Extraction = field(default_factory=Extraction)
    new_claims: list[dict] = field(default_factory=list)
    clarified: bool = False
    accepted_offer: dict | None = None
    target: dict | None = None
    segments: list[Segment] = field(default_factory=list)
    writes: int = 0
    slot_obs: dict[str, tuple[Slot, datetime]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    prose: str = ""
    injection: InjectionScan | None = None
    proposals: list = field(default_factory=list)
    plan_messages: list = field(default_factory=list)

    @property
    def conn(self):
        return self.ctx.conn

    @property
    def customer_id(self) -> str:
        return self.user["customer_id"]

    @property
    def session_id(self) -> str:
        return self.session["id"]

    def log(self, event_type: str, payload: dict | None = None) -> None:
        log_event(self.conn, self.ctx.clock.now(), event_type, payload or {}, self.user["id"], self.session_id)
        self.events.append(event_type)

    def add(self, kind: str, key: str, booking_id: str | None = None, **params) -> None:
        if booking_id and any(s.booking_id == booking_id and s.kind == kind for s in self.segments):
            return
        self.segments.append(Segment(kind, key, params, booking_id))

    def has(self, kind: str) -> bool:
        return any(segment.kind == kind for segment in self.segments)

    def booking_ids(self) -> list[str]:
        return [s.booking_id for s in self.segments if s.kind in BOOKING_KINDS and s.booking_id]
