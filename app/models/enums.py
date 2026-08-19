"""Shared enumerations used across models, schemas, and services."""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    RECEPTION = "RECEPTION"
    KITCHEN = "KITCHEN"


class PlatformRole(enum.StrEnum):
    """Reach across the whole platform, set directly on the user row.

    Deliberately separate from :class:`UserRole`, which describes what someone
    does inside their own venue. A super admin is still an OWNER of their own
    kitchen; this only says whether they may act on everybody else's.
    """

    USER = "USER"
    SUPER_ADMIN = "SUPER_ADMIN"


class ApprovalStatus(enum.StrEnum):
    WAITLIST = "WAITLIST"
    APPROVED = "APPROVED"


class VenueKind(enum.StrEnum):
    RESTAURANT = "RESTAURANT"
    HOTEL = "HOTEL"
    CAFE = "CAFE"


class QrKind(enum.StrEnum):
    TABLE = "TABLE"
    REVIEW = "REVIEW"


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

# The forward happy path. Staff see three stages, but every hop along this chain
# is still written to order_status_history — the UI is simplified, the record is not.
HAPPY_PATH: tuple[OrderStatus, ...] = (
    OrderStatus.PENDING,
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.COMPLETED,
)


def path_between(current: OrderStatus, target: OrderStatus) -> list[OrderStatus]:
    """Every status to pass through to get from ``current`` to ``target``.

    Empty when the move is not a forward step on the happy path.
    """
    if current not in HAPPY_PATH or target not in HAPPY_PATH:
        return []
    start = HAPPY_PATH.index(current)
    end = HAPPY_PATH.index(target)
    if end <= start:
        return []
    return list(HAPPY_PATH[start + 1 : end + 1])


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


class PlanTier(enum.StrEnum):
    BASIC = "BASIC"
    PRO = "PRO"


class SubscriptionStatus(enum.StrEnum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    GRACE = "GRACE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


class PlanRequestStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Statuses where the kitchen may keep using its paid feature set.
ENTITLED_STATUSES: frozenset[SubscriptionStatus] = frozenset(
    {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.GRACE}
)


class WaiterCallStatus(enum.StrEnum):
    PENDING = "PENDING"
    ACKED = "ACKED"


class OfferKind(enum.StrEnum):
    PERCENT = "PERCENT"
    FLAT = "FLAT"
    BOGO = "BOGO"
    COMBO = "COMBO"
    HAPPY_HOUR = "HAPPY_HOUR"
    SPECIAL_DAY = "SPECIAL_DAY"


class OfferState(enum.StrEnum):
    """Derived from ``is_active`` plus the offer window — never stored."""

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    EXPIRED = "EXPIRED"


class AnalyticsEventType(enum.StrEnum):
    QR_SCAN = "QR_SCAN"
    MENU_VIEW = "MENU_VIEW"
    ITEM_VIEW = "ITEM_VIEW"
    CATEGORY_FILTER = "CATEGORY_FILTER"
    OFFER_VIEW = "OFFER_VIEW"
    UPSELL_ACCEPTED = "UPSELL_ACCEPTED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_COMPLETED = "ORDER_COMPLETED"


# Event types a public (unauthenticated) client is allowed to log.
PUBLIC_EVENT_TYPES: frozenset[AnalyticsEventType] = frozenset(
    {
        AnalyticsEventType.QR_SCAN,
        AnalyticsEventType.MENU_VIEW,
        AnalyticsEventType.ITEM_VIEW,
        AnalyticsEventType.CATEGORY_FILTER,
        AnalyticsEventType.OFFER_VIEW,
    }
)
