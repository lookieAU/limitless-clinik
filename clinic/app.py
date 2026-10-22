import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from clinic import admin, api
from clinic.context import ClinicContext, build_context
from clinic.repo import ClinicError


def create_app(ctx: ClinicContext | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(title="Clinik clinic mock")
    app.state.ctx = ctx or build_context()
    app.include_router(api.router)
    app.include_router(admin.router)

    @app.exception_handler(ClinicError)
    async def clinic_error(_: Request, error: ClinicError) -> JSONResponse:
        return JSONResponse(error.body(), status_code=error.status)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "clinic"}

    return app
