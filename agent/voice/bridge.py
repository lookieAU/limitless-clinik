from dataclasses import dataclass

import httpx

from agent.memory.negation_lexicon import is_negation, tokenize
from agent.pipeline.language import detect_language

CONFIDENCE_FLOOR = 0.85
YES = frozenset("yes yeah yep yup right correct sure haan haa ha ji sahi bilkul हाँ हां जी सही".split())
GOODBYE = frozenset("bye goodbye thanks thank dhanyavaad dhanyawad shukriya अलविदा धन्यवाद शुक्रिया".split())
FILLER = {"en": "One moment.", "hi": "एक पल।"}
CONFIRM = {"en": "Just to be sure, you said: “{text}”. Is that right?", "hi": "पक्का कर लूँ, आपने कहा: “{text}”. सही है?"}


@dataclass
class VoiceReply:
    text: str
    filler: str | None = None


def needs_confirmation(text: str, confidence: float | None) -> bool:
    negated = any(is_negation(token) for token in tokenize(text))
    return negated and (confidence is None or confidence < CONFIDENCE_FLOOR)


def is_yes(text: str) -> bool:
    tokens = tokenize(text)
    return bool(tokens) and tokens[0] in YES


def is_goodbye(text: str) -> bool:
    return any(token in GOODBYE for token in tokenize(text))


def speakable(reply: str) -> str:
    return " ".join(part.strip() for part in reply.split("\n\n") if part.strip())


class VoiceBridge:
    def __init__(self, client: httpx.AsyncClient, user_id: str):
        self.client = client
        self.user_id = user_id
        self.pending: str | None = None

    async def login(self, fallback_user: str | None = None) -> None:
        response = await self.client.post("/api/login/code", json={"user_id": self.user_id})
        if response.status_code == 404 and fallback_user:
            self.user_id = fallback_user
            response = await self.client.post("/api/login/code", json={"user_id": self.user_id})
        response.raise_for_status()
        (await self.client.post("/api/login", json={"user_id": self.user_id, "code": response.json()["code"]})).raise_for_status()

    async def preferred_lang(self) -> str:
        response = await self.client.get("/api/state")
        response.raise_for_status()
        return "hi" if response.json()["user"]["preferred_lang"] == "hi" else "en"

    async def send(self, text: str, recap: bool = False) -> VoiceReply:
        lang = detect_language(text)
        response = await self.client.post("/api/chat", json={"text": text, "recap": recap})
        response.raise_for_status()
        return VoiceReply(speakable(response.json()["reply"]), FILLER[lang])

    async def respond(self, text: str, confidence: float | None = None) -> VoiceReply:
        if self.pending:
            original, self.pending = self.pending, None
            if is_yes(text):
                return await self.send(original)
        if needs_confirmation(text, confidence):
            self.pending = text
            return VoiceReply(CONFIRM[detect_language(text)].format(text=text))
        return await self.send(text, recap=is_goodbye(text))
