"""Aggregate queries behind the dashboard insights screen.

Everything here is read-only and scoped by ``restaurant_id``. Aggregation runs
in Postgres — a simple event table plus GROUP BY is enough at MVP scan volume
(PRD §20); no analytics warehouse until it isn't.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Numeric, cast, func, select

from app.models.analytics import AnalyticsEvent
from app.models.enums import AnalyticsEventType, OrderStatus
from app.models.menu import Category, MenuItem, MenuItemUpsell
from app.models.offer import Offer
from app.models.order import Order, OrderItem
from app.repositories.base import BaseRepository

# Order states that represent revenue actually earned.
REVENUE_STATUSES: tuple[OrderStatus, ...] = (
    OrderStatus.SERVED,
    OrderStatus.COMPLETED,
)


class AnalyticsRepository(BaseRepository[AnalyticsEvent]):
    model = AnalyticsEvent

    # ── Event counts ─────────────────────────────────────────
    async def event_counts(
        self, restaurant_id: uuid.UUID, since: datetime
    ) -> dict[AnalyticsEventType, int]:
        result = await self.session.execute(
            select(AnalyticsEvent.event_type, func.count())
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
            )
            .group_by(AnalyticsEvent.event_type)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def unique_visitors(self, restaurant_id: uuid.UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(AnalyticsEvent.visitor_key))).where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.visitor_key.is_not(None),
            )
        )
        return int(result.scalar_one() or 0)

    async def repeat_visitors(
        self, restaurant_id: uuid.UUID, since: datetime, timezone: str
    ) -> int:
        """Visitors seen on more than one distinct local day."""
        day = func.date(func.timezone(timezone, AnalyticsEvent.created_at))
        per_visitor = (
            select(AnalyticsEvent.visitor_key.label("visitor"))
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.visitor_key.is_not(None),
            )
            .group_by(AnalyticsEvent.visitor_key)
            .having(func.count(func.distinct(day)) > 1)
            .subquery()
        )
        result = await self.session.execute(select(func.count()).select_from(per_visitor))
        return int(result.scalar_one() or 0)

    async def scans_by_day(
        self, restaurant_id: uuid.UUID, since: datetime, timezone: str
    ) -> list[tuple[date, int]]:
        day = func.date(func.timezone(timezone, AnalyticsEvent.created_at)).label("day")
        result = await self.session.execute(
            select(day, func.count())
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == AnalyticsEventType.QR_SCAN,
            )
            .group_by(day)
            .order_by(day)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def table_scans(
        self, restaurant_id: uuid.UUID, since: datetime, limit: int = 20
    ) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(AnalyticsEvent.table_number, func.count().label("hits"))
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == AnalyticsEventType.QR_SCAN,
                AnalyticsEvent.table_number.is_not(None),
            )
            .group_by(AnalyticsEvent.table_number)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [(row[0], int(row[1])) for row in result.all()]

    async def top_viewed_items(
        self, restaurant_id: uuid.UUID, since: datetime, limit: int = 10
    ) -> list[tuple[uuid.UUID, str, int]]:
        result = await self.session.execute(
            select(MenuItem.id, MenuItem.name, func.count().label("hits"))
            .join(AnalyticsEvent, AnalyticsEvent.target_id == MenuItem.id)
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == AnalyticsEventType.ITEM_VIEW,
            )
            .group_by(MenuItem.id, MenuItem.name)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def offer_views(
        self, restaurant_id: uuid.UUID, since: datetime, limit: int = 10
    ) -> list[tuple[uuid.UUID, str, int]]:
        result = await self.session.execute(
            select(Offer.id, Offer.title, func.count().label("hits"))
            .join(AnalyticsEvent, AnalyticsEvent.target_id == Offer.id)
            .where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == AnalyticsEventType.OFFER_VIEW,
            )
            .group_by(Offer.id, Offer.title)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def upsell_impact(self, restaurant_id: uuid.UUID, since: datetime) -> tuple[int, Decimal]:
        """Accepted upsells and the revenue frozen against them at order time."""
        amount = cast(AnalyticsEvent.meta["amount"].as_string(), Numeric(10, 2))
        result = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(amount), 0)).where(
                AnalyticsEvent.restaurant_id == restaurant_id,
                AnalyticsEvent.created_at >= since,
                AnalyticsEvent.event_type == AnalyticsEventType.UPSELL_ACCEPTED,
            )
        )
        row = result.one()
        return int(row[0] or 0), Decimal(row[1] or 0)

    # ── Order-derived aggregates ─────────────────────────────
    async def order_counts(self, restaurant_id: uuid.UUID, since: datetime) -> tuple[int, int]:
        """(orders placed, orders completed) in the window."""
        result = await self.session.execute(
            select(
                func.count(),
                func.count().filter(Order.status == OrderStatus.COMPLETED),
            ).where(Order.restaurant_id == restaurant_id, Order.created_at >= since)
        )
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0)

    async def revenue(self, restaurant_id: uuid.UUID, since: datetime) -> tuple[Decimal, int]:
        """(revenue, order count) for orders that actually reached the table."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(Order.total), 0), func.count()).where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= since,
                Order.status.in_(REVENUE_STATUSES),
            )
        )
        row = result.one()
        return Decimal(row[0] or 0), int(row[1] or 0)

    async def peak_hours(
        self, restaurant_id: uuid.UUID, since: datetime, timezone: str
    ) -> list[tuple[int, int]]:
        hour = func.extract("hour", func.timezone(timezone, Order.created_at)).label("hour")
        result = await self.session.execute(
            select(hour, func.count())
            .where(Order.restaurant_id == restaurant_id, Order.created_at >= since)
            .group_by(hour)
            .order_by(hour)
        )
        return [(int(row[0]), int(row[1])) for row in result.all()]

    async def popular_categories(
        self, restaurant_id: uuid.UUID, since: datetime, limit: int = 10
    ) -> list[tuple[uuid.UUID, str, int]]:
        units = func.coalesce(func.sum(OrderItem.quantity), 0)
        result = await self.session.execute(
            select(Category.id, Category.name, units.label("units"))
            .join(MenuItem, MenuItem.category_id == Category.id)
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.restaurant_id == restaurant_id, Order.created_at >= since)
            .group_by(Category.id, Category.name)
            .order_by(units.desc())
            .limit(limit)
        )
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def top_ordered_items(
        self, restaurant_id: uuid.UUID, since: datetime, limit: int = 10
    ) -> list[tuple[uuid.UUID | None, str, int]]:
        units = func.coalesce(func.sum(OrderItem.quantity), 0)
        result = await self.session.execute(
            select(OrderItem.menu_item_id, OrderItem.name_snapshot, units.label("units"))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.restaurant_id == restaurant_id, Order.created_at >= since)
            .group_by(OrderItem.menu_item_id, OrderItem.name_snapshot)
            .order_by(units.desc())
            .limit(limit)
        )
        return [(row[0], row[1], int(row[2])) for row in result.all()]

    async def item_sales(
        self, restaurant_id: uuid.UUID, since: datetime
    ) -> dict[uuid.UUID, tuple[int, Decimal]]:
        """Units sold and revenue per live menu item, keyed by menu item id."""
        units = func.coalesce(func.sum(OrderItem.quantity), 0)
        revenue = func.coalesce(func.sum(OrderItem.subtotal), 0)
        result = await self.session.execute(
            select(OrderItem.menu_item_id, units, revenue)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.created_at >= since,
                OrderItem.menu_item_id.is_not(None),
            )
            .group_by(OrderItem.menu_item_id)
        )
        return {row[0]: (int(row[1]), Decimal(row[2] or 0)) for row in result.all()}

    async def upsell_pairs_in_order(self, order_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """(source item, suggested item) pairs where both are on this order."""
        source = select(OrderItem.menu_item_id).where(OrderItem.order_id == order_id).subquery()
        result = await self.session.execute(
            select(MenuItemUpsell.menu_item_id, MenuItemUpsell.suggested_item_id)
            .join(source, source.c.menu_item_id == MenuItemUpsell.menu_item_id)
            .where(
                MenuItemUpsell.suggested_item_id.in_(
                    select(OrderItem.menu_item_id).where(OrderItem.order_id == order_id)
                )
            )
        )
        return [(row[0], row[1]) for row in result.all()]

    async def item_sales_for_order(self, order_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
        """Line-item revenue on one order, keyed by menu item id."""
        result = await self.session.execute(
            select(OrderItem.menu_item_id, func.coalesce(func.sum(OrderItem.subtotal), 0))
            .where(OrderItem.order_id == order_id, OrderItem.menu_item_id.is_not(None))
            .group_by(OrderItem.menu_item_id)
        )
        return {row[0]: Decimal(row[1] or 0) for row in result.all()}

    async def attributed_upsell_targets(self, order_id: uuid.UUID) -> set[uuid.UUID]:
        """Upsell targets already credited to this order.

        Lets attribution run again when a diner appends items to an open ticket
        without double-counting what was already banked.
        """
        result = await self.session.execute(
            select(AnalyticsEvent.target_id).where(
                AnalyticsEvent.event_type == AnalyticsEventType.UPSELL_ACCEPTED,
                AnalyticsEvent.meta["orderId"].as_string() == str(order_id),
                AnalyticsEvent.target_id.is_not(None),
            )
        )
        return {row[0] for row in result.all() if row[0] is not None}
