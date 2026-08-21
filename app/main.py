"""Application entrypoint.

Wires FastAPI (REST) together with the Socket.IO server into a single ASGI
app. Run with ``uvicorn app.main:app``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RequestContextMiddleware

# Import registers the Socket.IO event handlers as a side effect.
from app.sockets import events as _socket_events  # noqa: F401
from app.sockets.server import sio

configure_logging(settings.debug)
logger = get_logger("aahaar")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s in %s mode", settings.app_name, settings.environment)
    yield
    from app.core.database import engine

    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.browser_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(GZipMiddleware, minimum_size=500)

    register_exception_handlers(application)
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    # Unauthenticated on purpose, and answers HEAD as well as GET.
    @application.api_route("/health", methods=["GET", "HEAD"], tags=["health"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": settings.app_name,
            "environment": settings.environment,
            # True when GEMINI_API_KEY is present — never exposes the key itself.
            "menuScan": settings.gemini_enabled,
        }

    @application.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs", "health": "/health"}

    return application


fastapi_app = create_app()

# The combined ASGI app: Socket.IO handles ``/socket.io/*``, FastAPI the rest.
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
