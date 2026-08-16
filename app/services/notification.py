"""Emits realtime Socket.IO events after successful DB commits.

Payloads are kept small (realtime.md §6). Dashboards/customers always have a
REST recovery path, so a dropped event never corrupts state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models.order import Order
from app.sockets.server import order_room, restaurant_room, sio


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


class NotificationService:
    """Thin wrapper around ``sio.emit`` for order lifecycle events."""

    async def order_created(self, order: Order) -> None:
        await sio.emit(
            "order:created",
            _order_event_payload(order),
            room=restaurant_room(order.restaurant_id),
        )

    async def order_status_changed(self, order: Order) -> None:
        payload = _order_event_payload(order)
        # Customer tracking channel.
        await sio.emit("order:status_updated", payload, room=order_room(order.id))
        # Dashboard list refresh signal.
        await sio.emit("order:updated", payload, room=restaurant_room(order.restaurant_id))

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


def get_notification_service() -> NotificationService:
    return NotificationService()
