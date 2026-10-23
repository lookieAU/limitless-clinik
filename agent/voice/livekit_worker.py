import asyncio
import logging
import os

import httpx
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, StopResponse, inference

from agent.voice.bridge import VoiceBridge, handle_turn
from agent.voice.token import AGENT_NAME

AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
STT_MODEL = os.environ.get("VOICE_STT_MODEL", "deepgram/nova-3")
TTS_MODEL = os.environ.get("VOICE_TTS_MODEL", "cartesia/sonic-3")
TTS_VOICE = os.environ.get("VOICE_TTS_VOICE", "")
DEFAULT_USER = os.environ.get("VOICE_DEFAULT_USER", "u_asha")
GREETING = {"en": "Hi, this is Clinik. I can book, move or cancel your appointment.", "hi": "नमस्ते, मैं Clinik हूँ। मैं आपकी अपॉइंटमेंट बुक, बदल या रद्द कर सकता हूँ।"}


class ClinikVoice(Agent):
    def __init__(self, bridge: VoiceBridge):
        super().__init__(instructions="Transport only: every reply comes from Clinik's turn pipeline.")
        self.bridge = bridge

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        await handle_turn(self.bridge, self.session.say, new_message.text_content or "", new_message.transcript_confidence)
        raise StopResponse()


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def clinik_call(ctx: agents.JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    bridge = VoiceBridge(httpx.AsyncClient(base_url=AGENT_URL, timeout=60.0), participant.identity)
    await bridge.login(fallback_user=DEFAULT_USER)
    lang = await bridge.preferred_lang()
    tts = inference.TTS(model=TTS_MODEL, language=lang, **({"voice": TTS_VOICE} if TTS_VOICE else {}))
    session = AgentSession(stt=inference.STT(model=STT_MODEL, language="multi"), tts=tts)
    await session.start(room=ctx.room, agent=ClinikVoice(bridge))
    await session.say(GREETING[lang])


async def idle() -> None:
    logging.getLogger("clinik.voice").warning("LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET not set; voice is off")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    if os.environ.get("LIVEKIT_URL") and os.environ.get("LIVEKIT_API_KEY") and os.environ.get("LIVEKIT_API_SECRET"):
        agents.cli.run_app(server)
    else:
        logging.basicConfig(level=logging.INFO)
        asyncio.run(idle())
