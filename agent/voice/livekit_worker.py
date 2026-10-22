import os

import httpx
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, ChatMessage, inference

from agent.voice.bridge import VoiceBridge

AGENT_URL = os.environ.get("AGENT_URL", "http://agent:8000")
STT_MODEL = os.environ.get("VOICE_STT_MODEL", "deepgram/nova-3")
TTS_MODEL = os.environ.get("VOICE_TTS_MODEL", "cartesia/sonic-3")
TTS_VOICE = os.environ.get("VOICE_TTS_VOICE", "")
TTS_LANGUAGE = os.environ.get("VOICE_TTS_LANGUAGE", "hi")


class ClinikVoice(Agent):
    def __init__(self, bridge: VoiceBridge):
        super().__init__(instructions="Transport only: every reply comes from Clinik's turn pipeline.")
        self.bridge = bridge

    async def llm_node(self, chat_ctx, tools, model_settings):
        latest = next((item for item in reversed(chat_ctx.items) if isinstance(item, ChatMessage) and item.role == "user"), None)
        if latest is None:
            return
        reply = await self.bridge.respond(latest.text_content or "", latest.transcript_confidence)
        if reply.filler:
            self.session.say(reply.filler, add_to_chat_ctx=False)
        yield reply.text


server = AgentServer()


@server.rtc_session(agent_name="clinik")
async def clinik_call(ctx: agents.JobContext) -> None:
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    client = httpx.AsyncClient(base_url=AGENT_URL, timeout=30.0)
    bridge = VoiceBridge(client, participant.identity)
    await bridge.login()
    tts = inference.TTS(model=TTS_MODEL, language=TTS_LANGUAGE, **({"voice": TTS_VOICE} if TTS_VOICE else {}))
    session = AgentSession(stt=inference.STT(model=STT_MODEL, language="multi"), tts=tts)
    await session.start(room=ctx.room, agent=ClinikVoice(bridge))
    await session.say("Namaste! Clinik here — I can book, move or cancel your appointment.")


if __name__ == "__main__":
    agents.cli.run_app(server)
