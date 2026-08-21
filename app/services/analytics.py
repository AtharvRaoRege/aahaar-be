"""Engagement analytics, the savings counter, and the menu-engineering matrix.

Basic sees scan/view/order counts. Pro sees visitor identity, revenue depth, and
the two numbers an owner actually renews for: how much aggregator commission the
direct orders avoided, and which dishes are worth keeping.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.core.plans import (
    AGGREGATOR_COMMISSION_RATE,
    PlanFeature,
    has_feature,
    spec_for,
)
from app.models.analytics import AnalyticsEvent
from app.models.enums import (
    PUBLIC_EVENT_TYPES,
    AnalyticsEventType,
    PlanTier,
)
from app.repositories.analytics import AnalyticsRepository
from app.repositories.menu import CategoryRepository, MenuItemRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.analytics import (
    AnalyticsSummary,
    CommissionSavings,
    DayPoint,
    DishPerformanceResponse,
    DishRow,
    HourPoint,
    LogEventRequest,
    NamedCount,
    UpsellImpact,
)
from app.services.subscription import SubscriptionService

logger = get_logger("aahaar.analytics")

MAX_RANGE_DAYS = 365
DEFAULT_RANGE_DAYS = 30

TOP_DISH_LIMIT = 8
SLOW_DISH_LIMIT = 8

# Verdicts are relative to the best-selling dish on the menu.
TOP_SHARE = 0.6
SLOW_SHARE = 0.15

# Below this many units the menu simply has not sold enough to call anything slow.
MIN_UNITS_FOR_SLOW = 20

VERDICT_TOP = "TOP"
VERDICT_STEADY = "STEADY"
VERDICT_SLOW = "SLOW"
VERDICT_NONE = "NONE"


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = AnalyticsRepository(session)
        self.items = MenuItemRepository(session)
        self.categories = CategoryRepository(session)
        self.restaurants = RestaurantRepository(session)

    # ── Event ingestion ──────────────────────────────────────
    async def log_public(self, restaurant_id: uuid.UUID, payload: LogEventRequest) -> None:
        """Record one event from an unauthenticated customer client."""
        if payload.event_type not in PUBLIC_EVENT_TYPES:
            raise ValidationError("That event type cannot be logged from a public client.")
        await self.log(
            restaurant_id,
            payload.event_type,
            customer_session_id=payload.customer_session_id,
            table_number=payload.table_number,
            visitor_key=payload.visitor_key,
            target_id=payload.target_id,
            meta=payload.meta,
            commit=True,
        )

    async def log(
        self,
        restaurant_id: uuid.UUID,
        event_type: AnalyticsEventType,
        *,
        customer_session_id: uuid.UUID | None = None,
        table_number: str | None = None,
        visitor_key: str | None = None,
        target_id: uuid.UUID | None = None,
        meta: dict | None = None,
        commit: bool = False,
    ) -> None:
        self.events.add(
            AnalyticsEvent(
                restaurant_id=restaurant_id,
                event_type=event_type,
                customer_session_id=customer_session_id,
                table_number=(table_number or None),
                visitor_key=(visitor_key or None),
                target_id=target_id,
                meta=meta,
            )
        )
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def log_order_upsells(self, order_id: uuid.UUID, restaurant_id: uuid.UUID) -> None:
        """Freeze upsell attribution at order time.

        Attribution must not move when the owner later edits their pairings, so
        the accepted suggestion and its value are snapshotted here, the same way
        item prices are.
        """
        pairs = await self.events.upsell_pairs_in_order(order_id)
        if not pairs:
            return
        already = await self.events.attributed_upsell_targets(order_id)
        sales = await self.events.item_sales_for_order(order_id)
        for source_id, suggested_id in pairs:
            if suggested_id in already:
                continue
            amount = sales.get(suggested_id)
            if amount is None:
                continue
            already.add(suggested_id)
            await self.log(
                restaurant_id,
                AnalyticsEventType.UPSELL_ACCEPTED,
                target_id=suggested_id,
                meta={
                    "amount": str(amount),
                    "sourceItemId": str(source_id),
                    "orderId": str(order_id),
                },
            )

    # ── Dashboard summary ────────────────────────────────────
    async def summary(
        self,
        restaurant_id: uuid.UUID,
        range_days: int,
        *,
        elevate_pro: bool = False,
    ) -> AnalyticsSummary:
        range_days = self._clamp_range(range_days)
        since = self._since(range_days)
        timezone = await self._timezone(restaurant_id)
        plan = PlanTier.PRO if elevate_pro else await self._plan(restaurant_id)
        is_pro = has_feature(plan, PlanFeature.ADVANCED_ANALYTICS)

        counts = await self.events.event_counts(restaurant_id, since)
        placed, completed = await self.events.order_counts(restaurant_id, since)
        categories = await self.events.popular_categories(restaurant_id, since)

        summary = AnalyticsSummary(
            range_days=range_days,
            plan=plan.value,
            is_pro=is_pro,
            qr_scans=counts.get(AnalyticsEventType.QR_SCAN, 0),
            menu_views=counts.get(AnalyticsEventType.MENU_VIEW, 0),
            orders_placed=placed,
            orders_completed=completed,
            popular_categories=[
                NamedCount(id=row[0], label=row[1], count=row[2]) for row in categories
            ],
            offer_views=[
                NamedCount(id=row[0], label=row[1], count=row[2])
                for row in await self.events.offer_views(restaurant_id, since)
            ],
        )
        if not is_pro:
            return summary

        revenue, revenue_orders = await self.events.revenue(restaurant_id, since)
        upsell_count, upsell_revenue = await self.events.upsell_impact(restaurant_id, since)

        summary.unique_visitors = await self.events.unique_visitors(restaurant_id, since)
        summary.repeat_visitors = await self.events.repeat_visitors(restaurant_id, since, timezone)
        summary.total_revenue = self._money(revenue)
        summary.average_order_value = self._money(
            revenue / revenue_orders if revenue_orders else Decimal("0")
        )
        summary.top_viewed_items = [
            NamedCount(id=row[0], label=row[1], count=row[2])
            for row in await self.events.top_viewed_items(restaurant_id, since)
        ]
        summary.top_ordered_items = [
            NamedCount(id=row[0], label=row[1], count=row[2])
            for row in await self.events.top_ordered_items(restaurant_id, since)
        ]
        summary.table_scans = [
            NamedCount(id=None, label=row[0], count=row[1])
            for row in await self.events.table_scans(restaurant_id, since)
        ]
        summary.peak_hours = [
            HourPoint(hour=row[0], count=row[1])
            for row in await self.events.peak_hours(restaurant_id, since, timezone)
        ]
        summary.scans_by_day = [
            DayPoint(day=row[0], count=row[1])
            for row in await self.events.scans_by_day(restaurant_id, since, timezone)
        ]
        summary.commission_savings = self._commission_savings(
            revenue, revenue_orders, plan, range_days
        )
        summary.upsell_impact = UpsellImpact(
            accepted_count=upsell_count,
            attributed_revenue=self._money(upsell_revenue),
        )
        return summary

    # ── Dish performance ─────────────────────────────────────
    async def dish_performance(
        self, restaurant_id: uuid.UUID, range_days: int
    ) -> DishPerformanceResponse:
        """Which dishes are carrying the menu, and which are just taking up room.

        Ranked purely on units sold and revenue. There is deliberately no margin
        axis: it would require every owner to maintain a cost price for every
        dish, and almost none of them will.
        """
        range_days = self._clamp_range(range_days)
        since = self._since(range_days)
        items = await self.items.list_by_restaurant(restaurant_id)
        sales = await self.events.item_sales(restaurant_id, since)
        categories = {
            category.id: category.name
            for category in await self.categories.list_by_restaurant(restaurant_id)
        }

        total_units = sum(units for units, _ in sales.values())
        best_units = max((units for units, _ in sales.values()), default=0)

        rows: list[DishRow] = []
        for item in items:
            units, revenue = sales.get(item.id, (0, Decimal("0")))
            rows.append(
                DishRow(
                    menu_item_id=item.id,
                    name=item.name,
                    category=categories.get(item.category_id),
                    price=item.base_price,
                    units_sold=units,
                    revenue=self._money(revenue),
                    share_of_orders=(round(units / total_units * 100, 1) if total_units else 0.0),
                    verdict=self._verdict(units, best_units),
                )
            )

        rows.sort(key=lambda row: (-row.units_sold, -float(row.revenue), row.name))
        top = [row for row in rows if row.units_sold > 0][:TOP_DISH_LIMIT]
        # Only call a dish slow once the menu has enough sales to judge it by.
        slow = (
            [row for row in reversed(rows) if row.units_sold == 0][:SLOW_DISH_LIMIT]
            if total_units >= MIN_UNITS_FOR_SLOW
            else []
        )
        return DishPerformanceResponse(
            range_days=range_days,
            top=top,
            slow=slow,
            total_units=total_units,
        )

    # ── Internals ────────────────────────────────────────────
    def _verdict(self, units: int, best_units: int) -> str:
        if units == 0:
            return VERDICT_NONE
        if best_units and units >= best_units * TOP_SHARE:
            return VERDICT_TOP
        if best_units and units <= best_units * SLOW_SHARE:
            return VERDICT_SLOW
        return VERDICT_STEADY

    def _commission_savings(
        self, revenue: Decimal, order_count: int, plan: PlanTier, range_days: int
    ) -> CommissionSavings:
        """What the same orders would have cost through a delivery aggregator."""
        commission = self._money(revenue * AGGREGATOR_COMMISSION_RATE)
        months = Decimal(range_days) / Decimal("30")
        platform_cost = self._money(spec_for(plan).monthly_price * months)
        return CommissionSavings(
            direct_order_revenue=self._money(revenue),
            commission_rate=float(AGGREGATOR_COMMISSION_RATE),
            commission_avoided=commission,
            platform_cost=platform_cost,
            net_saving=self._money(commission - platform_cost),
            order_count=order_count,
        )

    def _clamp_range(self, range_days: int) -> int:
        if range_days <= 0:
            return DEFAULT_RANGE_DAYS
        return min(range_days, MAX_RANGE_DAYS)

    def _since(self, range_days: int) -> datetime:
        return datetime.now(UTC) - timedelta(days=range_days)

    def _money(self, value: Decimal) -> Decimal:
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def _timezone(self, restaurant_id: uuid.UUID) -> str:
        restaurant = await self.restaurants.get(restaurant_id)
        return restaurant.timezone if restaurant else "Asia/Kolkata"

    async def _plan(self, restaurant_id: uuid.UUID) -> PlanTier:
        subscription = await SubscriptionService(self.session).get_or_create(restaurant_id)
        return subscription.effective_plan
