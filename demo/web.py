import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent.ui.view import panel_context, reply_view
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

    @app.post("/replay/start")
    async def start() -> dict:
        if app.state.replay:
            await app.state.replay.harness.close()
            app.state.workdir.cleanup()
        app.state.workdir = tempfile.TemporaryDirectory()
        app.state.replay = await build_replay(Path(app.state.workdir.name))
        return {"total": len(app.state.replay.timeline["steps"])}

    @app.post("/replay/next")
    async def next_step() -> dict:
        replay = app.state.replay
        step = await replay.next()
        reply = reply_view(step.reply, step.result) if step.said else None
        panels = panel_context(replay.harness.agent_ctx, replay.user)
        return {
            "step": templates.get_template("_replay_step.html").render(step=step, reply=reply),
            "panels": templates.get_template("_panels.html").render(**panels),
            "position": replay.position,
            "total": len(replay.timeline["steps"]),
            "done": replay.done,
        }

    return app
