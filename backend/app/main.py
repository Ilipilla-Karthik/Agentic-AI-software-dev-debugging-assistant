from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .llm import get_provider
from .memory import memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await memory.remember("__system__", "system", "boot", {"provider": get_provider().name})
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Multi-agent software development & debugging assistant.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .api.routes import router

    app.include_router(router, prefix=settings.api_prefix)

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "provider": get_provider().name,
            "memory_backend": memory.backend,
        }

    return app


app = create_app()