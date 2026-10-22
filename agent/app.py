import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent import api, calendar_feed, webhooks_in
from agent.context import AgentContext, build_context
from agent.memory.scheduler import scheduler_loop
from agent.pipeline.sync import poll_all
from agent.ui import admin as ui_admin
from agent.ui import routes as ui_routes

log = logging.getLogger("agent")


async def poll_loop(ctx: AgentContext) -> None:
    while True:
        await asyncio.sleep(ctx.settings.poll_interval_s)
        try:
            await poll_all(ctx)
        except Exception:
            log.exception("background poll failed")


async def warm_embedder(ctx: AgentContext) -> None:
    await asyncio.to_thread(ctx.embedder.embed, ["warm up"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx: AgentContext = app.state.ctx
    tasks = []
    if ctx.settings.background_tasks:
        tasks = [
            asyncio.create_task(scheduler_loop(ctx)),
            asyncio.create_task(poll_loop(ctx)),
            asyncio.create_task(warm_embedder(ctx)),
        ]
    yield
    for task in tasks:
        task.cancel()


def create_app(ctx: AgentContext | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(title="Clinik by Limitless", lifespan=lifespan)
    app.state.ctx = ctx or build_context()
    app.include_router(api.router)
    app.include_router(webhooks_in.router)
    app.include_router(calendar_feed.router)
    app.include_router(ui_routes.router)
    app.include_router(ui_admin.router)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "ui" / "static"), name="static")
    ui_routes.templates.env.globals["replay_url"] = app.state.ctx.settings.replay_url

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "agent"}

    return app
