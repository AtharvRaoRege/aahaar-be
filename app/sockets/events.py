"""Socket.IO connection and room-join handlers.

- Dashboard clients authenticate (JWT) and may join their restaurant room.
- Customer clients join their order room by order id (knowing the id is the
  capability; no staff data is exposed on that channel).
"""

from __future__ import annotations

import uuid

import jwt

from app.core.database import SessionFactory
from app.core.logging import get_logger
from app.core.security import decode_token
from app.repositories.restaurant import RestaurantRepository
from app.repositories.user import UserRepository
from app.sockets.server import order_room, restaurant_room, sio

logger = get_logger("aahaar.sockets")


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> None:
    user_id: str | None = None
    token_sid: str | None = None
    token = (auth or {}).get("token") if auth else None
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") == "access":
                user_id = payload.get("sub")
                token_sid = payload.get("sid")
        except jwt.PyJWTError:
            user_id = None
    await sio.save_session(sid, {"user_id": user_id, "token_sid": token_sid})
    logger.debug("socket connected sid=%s authed=%s", sid, bool(user_id))


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("socket disconnected sid=%s", sid)


@sio.event
async def join_restaurant(sid: str, data: dict) -> dict:
    """Dashboard joins ``restaurant:{id}`` after verifying tenant ownership."""
    restaurant_id = (data or {}).get("restaurantId")
    if not restaurant_id:
        return {"ok": False, "error": "restaurantId is required"}

    session = await sio.get_session(sid)
    user_id = session.get("user_id")
    if not user_id:
        return {"ok": False, "error": "authentication required"}

    try:
        restaurant_uuid = uuid.UUID(str(restaurant_id))
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid identifier"}

    async with SessionFactory() as db:
        user = await UserRepository(db).get(user_uuid)
        if user is None or not user.is_active:
            return {"ok": False, "error": "invalid user"}
        token_sid = session.get("token_sid")
        if not token_sid or str(user.session_id) != str(token_sid):
            return {"ok": False, "error": "session replaced"}
        restaurant = await RestaurantRepository(db).get_for_tenant(restaurant_uuid, user.tenant_id)
        if restaurant is None and user.is_super_admin:
            restaurant = await RestaurantRepository(db).get(restaurant_uuid)
        if restaurant is None:
            return {"ok": False, "error": "forbidden"}

    await sio.enter_room(sid, restaurant_room(restaurant_uuid))
    return {"ok": True, "room": restaurant_room(restaurant_uuid)}


@sio.event
async def join_order(sid: str, data: dict) -> dict:
    """Customer joins its ``order:{id}`` room to receive status updates."""
    order_id = (data or {}).get("orderId")
    if not order_id:
        return {"ok": False, "error": "orderId is required"}
    try:
        order_uuid = uuid.UUID(str(order_id))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid identifier"}
    await sio.enter_room(sid, order_room(order_uuid))
    return {"ok": True, "room": order_room(order_uuid)}


@sio.event
async def leave_order(sid: str, data: dict) -> dict:
    order_id = (data or {}).get("orderId")
    if not order_id:
        return {"ok": False, "error": "orderId is required"}
    try:
        order_uuid = uuid.UUID(str(order_id))
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid identifier"}
    await sio.leave_room(sid, order_room(order_uuid))
    return {"ok": True}
