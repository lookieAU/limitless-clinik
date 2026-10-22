from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Clinik by Limitless")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "agent"}

    return app
