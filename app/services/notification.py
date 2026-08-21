from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.order import Order
from app.models.review import Review
from app.models.waiter_call import WaiterCall
from app.services.push import PushService
from app.sockets.server import order_room, restaurant_room, sio

logger = get_logger("aahaar.notify")


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _order_event_payload(order: Order) -> dict[str, Any]:
    return {
        "orderId": str(order.id),
        "orderNumber": order.order_number,
        "status": order.status.value,
        "restaurantId": str(order.restaurant_id),
        "total": float(order.total),
        "tableNumber": order.table_number,
        "roomNumber": order.room_number,
        "updatedAt": (order.updated_at or datetime.now(UTC)).isoformat()
        if order.updated_at
        else _iso_now(),
    }


def _waiter_event_payload(call: WaiterCall) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "restaurantId": str(call.restaurant_id),
        "tableNumber": call.table_number,
        "status": call.status.value,
        "createdAt": (call.created_at or datetime.now(UTC)).isoformat()
        if call.created_at
        else _iso_now(),
    }


def _review_event_payload(review: Review) -> dict[str, Any]:
    return {
        "reviewId": str(review.id),
        "restaurantId": str(review.restaurant_id),
        "orderId": str(review.order_id) if review.order_id else None,
        "rating": review.rating,
        "createdAt": (review.created_at or datetime.now(UTC)).isoformat(),
    }


class NotificationService:
    """Socket.IO (legacy) plus Web Push after a successful commit.

    Supabase Realtime automatically picks up Postgres changes for tables added
    to the `supabase_realtime` publication, so the frontend can migrate off
    Socket.IO without backend changes.
    """

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def order_created(self, order: Order) -> None:
        payload = _order_event_payload(order)
        table = order.table_number or order.room_number or "Walk-in"
        await asyncio.gather(
            sio.emit("order:created", payload, room=restaurant_room(order.restaurant_id)),
            self._push(
                order.restaurant_id,
                {
                    "type": "order",
                    "title": f"New order #{order.order_number}",
                    "body": f"Table {table} · ₹{float(order.total):.0f}",
                    "url": "/dashboard",
                    "tag": f"order:{order.id}",
                    "orderId": str(order.id),
                    "orderNumber": order.order_number,
                    "tableNumber": order.table_number,
                    "roomNumber": order.room_number,
                    "total": float(order.total),
                },
            ),
        )

    async def review_created(self, review: Review) -> None:
        payload = _review_event_payload(review)
        stars = "★" * review.rating
        await asyncio.gather(
            sio.emit("review:created", payload, room=restaurant_room(review.restaurant_id)),
            self._push(
                review.restaurant_id,
                {
                    "type": "review",
                    "title": f"New rating {stars}",
                    "body": "A guest just rated your venue.",
                    "url": "/dashboard/ratings",
                    "tag": f"review:{review.id}",
                    "reviewId": str(review.id),
                    "rating": review.rating,
                },
            ),
        )

    async def _push(self, restaurant_id: uuid.UUID, payload: dict[str, Any]) -> None:
        if self.session is None:
            return
        try:
            await PushService(self.session).send_to_restaurant(restaurant_id, payload)
        except Exception:
            logger.exception("Web push failed for restaurant %s", restaurant_id)

    async def order_items_added(self, order: Order) -> None:
        payload = _order_event_payload(order)
        payload["itemsAdded"] = True
        table = order.table_number or order.room_number or "Walk-in"
        await asyncio.gather(
            sio.emit("order:updated", payload, room=restaurant_room(order.restaurant_id)),
            sio.emit("order:status_updated", payload, room=order_room(order.id)),
            self._push(
                order.restaurant_id,
                {
                    "type": "order",
                    "title": f"Order #{order.order_number} updated",
                    "body": f"Table {table} added items · ₹{float(order.total):.0f}",
                    "url": "/dashboard",
                    "tag": f"order:{order.id}:items",
                    "orderId": str(order.id),
                    "orderNumber": order.order_number,
                    "tableNumber": order.table_number,
                    "roomNumber": order.room_number,
                    "total": float(order.total),
                    "itemsAdded": True,
                },
            ),
        )

    async def order_status_changed(self, order: Order) -> None:
        payload = _order_event_payload(order)
        await asyncio.gather(
            sio.emit("order:status_updated", payload, room=order_room(order.id)),
            sio.emit("order:updated", payload, room=restaurant_room(order.restaurant_id)),
        )

    async def order_accepted(self, order: Order) -> None:
        await sio.emit("order:accepted", _order_event_payload(order), room=order_room(order.id))
        await self._notify_restaurant(order)

    async def order_rejected(self, order: Order) -> None:
        await sio.emit("order:rejected", _order_event_payload(order), room=order_room(order.id))
        await self._notify_restaurant(order)

    async def _notify_restaurant(self, order: Order) -> None:
        await sio.emit(
            "order:updated",
            _order_event_payload(order),
            room=restaurant_room(order.restaurant_id),
        )

    async def waiter_called(self, call: WaiterCall) -> None:
        payload = _waiter_event_payload(call)
        table = call.table_number or "Walk-in"
        await asyncio.gather(
            sio.emit("waiter:called", payload, room=restaurant_room(call.restaurant_id)),
            self._push(
                call.restaurant_id,
                {
                    "type": "waiter",
                    "title": f"Waiter needed · Table {table}",
                    "body": "A guest asked for a waiter at this table.",
                    "url": "/dashboard/orders",
                    "tag": f"waiter:{call.id}",
                    "tableNumber": call.table_number,
                },
            ),
        )

    async def waiter_acked(self, call: WaiterCall) -> None:
        await sio.emit(
            "waiter:acked",
            _waiter_event_payload(call),
            room=restaurant_room(call.restaurant_id),
        )


def get_notification_service() -> NotificationService:
    return NotificationService()
