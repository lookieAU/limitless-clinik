from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Clinik clinic mock")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "clinic"}

    return app
