"""Socket.IO server instance and room-name helpers.

Realtime is a *notification* layer only — PostgreSQL remains the source of
truth (see realtime.md). Events are emitted by services **after** a successful
commit.
"""

from __future__ import annotations

import uuid

import socketio

from app.core.config import settings

_client_manager = socketio.AsyncRedisManager(settings.redis_url) if settings.redis_url else None

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.browser_origins or [],
    client_manager=_client_manager,
    logger=False,
    engineio_logger=False,
)


def restaurant_room(restaurant_id: uuid.UUID | str) -> str:
    return f"restaurant:{restaurant_id}"


def order_room(order_id: uuid.UUID | str) -> str:
    return f"order:{order_id}"
