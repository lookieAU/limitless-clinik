import json
from dataclasses import dataclass, field

from agent.repo import claims, verified
from agent.vocab import claim_label
from shared.sqlite import one


@dataclass
class MemoryView:
    summary_id: str | None = None
    day_local: str | None = None
    constraints: list[dict] = field(default_factory=list)
    snapshot: list[dict] = field(default_factory=list)

    def as_context(self) -> str:
        if not self.summary_id:
            return "No earlier memory."
        said = "; ".join(claim_label(item, "en") for item in self.constraints) or "nothing"
        seen = "; ".join(f"{item['ref']} {item['status']} as of {item['observed_utc']} (re-verify)" for item in self.snapshot) or "none"
        return f"Memory from {self.day_local} — CLAIMS the customer made: {said}. Old clinic snapshot: {seen}."


def load_memory(conn, user_id: str) -> MemoryView:
    row = one(
        conn,
        "SELECT * FROM memory_summaries WHERE user_id = ? AND validated = 1 ORDER BY day_local DESC, rowid DESC LIMIT 1",
        (user_id,),
    )
    if row is None:
        return MemoryView()
    structured = json.loads(row["structured_json"])
    overridden = claims.overridden_ids(conn, user_id)
    constraints = [item for item in structured["constraints"] if not set(item["claim_ids"]) <= overridden]
    snapshot = []
    for item in structured.get("clinic_snapshot", []):
        current = verified.get(conn, item["booking_id"])
        if current is None or current["observed_utc"] <= item["observed_utc"]:
            snapshot.append(item)
    return MemoryView(row["id"], row["day_local"], constraints, snapshot)
