"""Shared enumerations used across models, schemas, and services."""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    RECEPTION = "RECEPTION"
    KITCHEN = "KITCHEN"


class ApprovalStatus(enum.StrEnum):
    WAITLIST = "WAITLIST"
    APPROVED = "APPROVED"


class VenueKind(enum.StrEnum):
    RESTAURANT = "RESTAURANT"
    HOTEL = "HOTEL"
    CAFE = "CAFE"


class OrderStatus(enum.StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Terminal states cannot transition further.
TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.CANCELLED}
)

# Allowed forward transitions for the staff-driven lifecycle.
STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.ACCEPTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.ACCEPTED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.SERVED, OrderStatus.CANCELLED},
    OrderStatus.SERVED: {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
}

# Statuses considered "active" (need attention on the dashboard).
ACTIVE_STATUSES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.ACCEPTED,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        OrderStatus.SERVED,
    }
)
