import hashlib
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer

from agent.repo import sessions, users

COOKIE = "clinik_session"


@dataclass
class Auth:
    user: dict
    session: dict


def serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt="clinik-session")


def login_code(secret: str, user_id: str) -> str:
    digest = hmac.new(secret.encode(), f"otp:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"{int(digest[:8], 16) % 1_000_000:06d}"


def start_session(request: Request, response: Response, user: dict) -> dict:
    ctx = request.app.state.ctx
    session = sessions.create_session(ctx.conn, user, ctx.clock.now())
    token = serializer(ctx.settings.session_secret).dumps({"user_id": user["id"], "session_id": session["id"]})
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax")
    return session


def current_auth(request: Request) -> Auth | None:
    ctx = request.app.state.ctx
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        data = serializer(ctx.settings.session_secret).loads(token)
    except BadSignature:
        return None
    user = users.get_user(ctx.conn, data["user_id"])
    session = sessions.get_session(ctx.conn, data["session_id"])
    if user is None or session is None or session["user_id"] != user["id"]:
        return None
    return Auth(user, session)


def require_auth(request: Request) -> Auth:
    auth = current_auth(request)
    if auth is None:
        raise HTTPException(status_code=401, detail="login required")
    return auth
