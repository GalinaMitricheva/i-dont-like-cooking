from fastapi import FastAPI

from idlcooking import __version__
from idlcooking.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="I don't like cooking",
        version=__version__,
        description="Backend API for a Telegram-first weekly meal planning service.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    return app


app = create_app()
