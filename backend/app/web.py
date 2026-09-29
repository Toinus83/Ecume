"""Single-process deployment: built frontend at /, existing API at /api."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_DIR
from app.main import app as api


def create_app() -> FastAPI:
    frontend = Path(os.getenv("ECUME_FRONTEND_DIR", str(PROJECT_DIR / "frontend" / "dist")))
    if not (frontend / "index.html").is_file():
        raise RuntimeError("Frontend absent : compiler frontend ou utiliser l'image ECUME complete.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Mounted applications do not receive startup/shutdown automatically.
        async with api.router.lifespan_context(api):
            yield

    app = FastAPI(title="ECUME", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/api", api)
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app
