from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from agent.auth import Auth, login_code, require_auth, start_session
from agent.pipeline.turn import TurnResult, turn
from agent.repo import claims, users, verified
from agent.repo.audit import recent_events

router = APIRouter(prefix="/api")


class CodeRequest(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    user_id: str
    code: str


class ChatRequest(BaseModel):
    text: str
    client_msg_id: str | None = None


@router.post("/login/code")
async def request_code(body: CodeRequest, request: Request) -> dict:
    ctx = request.app.state.ctx
    if users.get_user(ctx.conn, body.user_id) is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return {"code": login_code(ctx.settings.session_secret, body.user_id), "note": "mock one-time code"}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response) -> dict:
    ctx = request.app.state.ctx
    user = users.get_user(ctx.conn, body.user_id)
    if user is None or body.code != login_code(ctx.settings.session_secret, body.user_id):
        raise HTTPException(status_code=401, detail="invalid code")
    session = start_session(request, response, user)
    return {"user_id": user["id"], "session_id": session["id"]}


@router.post("/session/new")
async def new_session(request: Request, response: Response, auth: Auth = Depends(require_auth)) -> dict:
    session = start_session(request, response, auth.user)
    return {"session_id": session["id"]}


@router.post("/chat")
async def chat(body: ChatRequest, request: Request, auth: Auth = Depends(require_auth)) -> TurnResult:
    return await turn(request.app.state.ctx, auth.user, auth.session, body.text, body.client_msg_id)


@router.get("/state")
async def state(request: Request, auth: Auth = Depends(require_auth)) -> dict:
    ctx = request.app.state.ctx
    return {
        "user": {key: auth.user[key] for key in ("id", "display_name", "tz", "preferred_lang")},
        "session": {"id": auth.session["id"], "state": auth.session["state"]},
        "verified": verified.for_customer(ctx.conn, auth.user["customer_id"]),
        "claims": claims.all_for_user(ctx.conn, auth.user["id"]),
        "events": recent_events(ctx.conn, auth.user["id"]),
    }
