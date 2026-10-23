from datetime import timedelta

from livekit import api

from agent.settings import AgentSettings

AGENT_NAME = "clinik"


def voice_token(settings: AgentSettings, user_id: str, session_id: str) -> dict:
    room = f"clinik-{session_id}"
    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(user_id)
        .with_ttl(timedelta(hours=1))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]))
        .to_jwt()
    )
    return {"url": settings.livekit_url, "token": token, "room": room}
