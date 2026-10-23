import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from agent.auth import COOKIE, current_auth, login_code, start_session
from agent.pipeline.turn import turn
from agent.repo import users
from agent.ui.view import history, panel_context, reply_view
from agent.voice.token import voice_token

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter()
MODES = ("chat", "voice")


def render(request: Request, name: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context)


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> Response:
    return RedirectResponse("/chat" if current_auth(request) else "/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return render(request, "login.html", users=users.list_users(request.app.state.ctx.conn))


@router.post("/login/start", response_class=HTMLResponse)
async def login_start(request: Request, user_id: str = Form(...)) -> HTMLResponse:
    ctx = request.app.state.ctx
    user = users.get_user(ctx.conn, user_id)
    return render(request, "code.html", user=user, code=login_code(ctx.settings.session_secret, user_id))


@router.post("/login/verify")
async def login_verify(request: Request, user_id: str = Form(...), code: str = Form(...)) -> Response:
    ctx = request.app.state.ctx
    user = users.get_user(ctx.conn, user_id)
    if user is None or code.strip() != login_code(ctx.settings.session_secret, user_id):
        return render(request, "code.html", user=user, code=None, error="That code didn't match.")
    response = RedirectResponse("/chat", status_code=303)
    start_session(request, response, user)
    return response


@router.get("/logout")
async def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    return response


@router.post("/session/new")
async def new_session(request: Request, mode: str = "chat") -> Response:
    auth = current_auth(request)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    response = RedirectResponse(f"/chat?mode={mode if mode in MODES else 'chat'}", status_code=303)
    start_session(request, response, auth.user)
    return response


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, mode: str = "chat") -> Response:
    auth = current_auth(request)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    ctx = request.app.state.ctx
    mode = mode if mode in MODES and (mode != "voice" or ctx.settings.voice_enabled) else "chat"
    return render(
        request,
        "chat.html",
        user=auth.user,
        mode=mode,
        voice_enabled=ctx.settings.voice_enabled,
        pairs=history(ctx, auth.session["id"]),
        **panel_context(ctx, auth.user),
    )


@router.post("/ui/send", response_class=HTMLResponse)
async def send(request: Request, text: str = Form(...), client_msg_id: str = Form("")) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    result = await turn(request.app.state.ctx, auth.user, auth.session, text.strip(), client_msg_id or None)
    return render(request, "_agent.html", reply=reply_view(result.reply, result.model_dump()))


@router.get("/ui/panels", response_class=HTMLResponse)
async def panels(request: Request) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    return render(request, "_panels.html", **panel_context(request.app.state.ctx, auth.user))


@router.get("/ui/voice/token")
async def voice(request: Request) -> Response:
    auth = current_auth(request)
    settings = request.app.state.ctx.settings
    if auth is None or not settings.voice_enabled:
        return Response(status_code=404)
    return JSONResponse(voice_token(settings, auth.user["id"], auth.session["id"]))


@router.get("/ui/stream")
async def stream(request: Request) -> Response:
    auth = current_auth(request)
    if auth is None:
        return Response(status_code=401)
    bus = request.app.state.ctx.bus
    queue = bus.subscribe(auth.user["id"])

    async def events():
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield {"event": "ping", "data": "."}
                    continue
                yield {"event": event, "data": "refresh"}
        finally:
            bus.unsubscribe(auth.user["id"], queue)

    return EventSourceResponse(events())
