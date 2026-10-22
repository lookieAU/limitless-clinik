import re
from dataclasses import dataclass

PATTERNS = {
    "override_rules": r"\b(ignore|disregard|forget|bypass|override)\b.{0,40}\b(rules?|instructions?|prompt|polic(y|ies)|guardrails?)\b",
    "role_play": r"\b(you are now|act as|pretend to be|developer mode|jailbreak|dan mode)\b",
    "prompt_markers": r"(^|\n)\s*(system|assistant|developer)\s*:|<\|[a-z_]+\|>|\[/?(inst|sys)\]",
    "bulk_action": r"\b(book|cancel|reserve|delete|reschedule)\b.{0,20}\b(all|every|each|everything)\b",
    "bulk_action_hi": r"(सारे|सभी|sab|saare)\s*(slot|स्लॉट|appointment|बुकिंग)",
}
MAX_LENGTH = 1200


@dataclass(frozen=True)
class InjectionScan:
    flagged: bool
    reasons: tuple[str, ...]

    @property
    def bulk(self) -> bool:
        return any(reason.startswith("bulk_action") for reason in self.reasons)


def scan(text: str) -> InjectionScan:
    lowered = text.lower()
    reasons = [name for name, pattern in PATTERNS.items() if re.search(pattern, lowered, re.IGNORECASE)]
    if len(text) > MAX_LENGTH:
        reasons.append("bulk_text")
    return InjectionScan(bool(reasons), tuple(reasons))
