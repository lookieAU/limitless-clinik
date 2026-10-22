import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.ui.view import panel_context, paragraphs
from demo.replay import build_replay, load_timeline

ROOT = Path(__file__).parent
AGENT_UI = ROOT.parent / "agent" / "ui"
templates = Jinja2Templates(directory=[ROOT / "templates", AGENT_UI / "templates"])


def create_app() -> FastAPI:
    app = FastAPI(title="Clinik replay")
    app.mount("/static", StaticFiles(directory=AGENT_UI / "static"), name="static")
    app.state.replay = None
    app.state.workdir = None

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "replay"}

    @app.get("/", response_class=HTMLResponse)
    @app.get("/replay", response_class=HTMLResponse)
    async def page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "replay.html", {"timeline": load_timeline()})

    @app.post("/replay/start", response_class=HTMLResponse)
    async def start(request: Request) -> HTMLResponse:
        if app.state.replay:
            await app.state.replay.harness.close()
            app.state.workdir.cleanup()
        app.state.workdir = tempfile.TemporaryDirectory()
        app.state.replay = await build_replay(Path(app.state.workdir.name))
        return templates.TemplateResponse(request, "_replay_controls.html", {"replay": app.state.replay, "fresh": True})

    @app.post("/replay/next", response_class=HTMLResponse)
    async def next_step(request: Request) -> HTMLResponse:
        replay = app.state.replay
        step = await replay.next()
        pair = None
        if step.said:
            pair = {"customer": {"text": step.said}, "agent": {"paragraphs": paragraphs(step.reply), "result": step.result}}
        context = {
            "step": step,
            "pair": pair,
            "replay": replay,
            "user": replay.user,
            **panel_context(replay.harness.agent_ctx, replay.user),
        }
        return templates.TemplateResponse(request, "_replay_step.html", context)

    return app
