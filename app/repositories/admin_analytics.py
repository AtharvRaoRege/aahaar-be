"""Platform-wide aggregates for the super-admin console."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ENTITLED_STATUSES, OrderStatus, PlanTier, UserRole
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.analytics import REVENUE_STATUSES

PLATFORM_TZ = ZoneInfo("Asia/Kolkata")


class AdminAnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _since(self, range_days: int) -> datetime:
        now = datetime.now(timezone.utc)
        return now - timedelta(days=max(1, range_days))

    def _today_start(self) -> datetime:
        local = datetime.now(PLATFORM_TZ).date()
        return datetime(local.year, local.month, local.day, tzinfo=PLATFORM_TZ).astimezone(
            timezone.utc
        )

    async def venue_counts(self) -> tuple[int, int, int, int]:
        """(total, live, pro, basic) venue counts."""
        total = await self.session.scalar(select(func.count()).select_from(Restaurant))
        live = await self.session.scalar(
            select(func.count()).select_from(Restaurant).where(Restaurant.is_published.is_(True))
        )
        pro = await self.session.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.plan == PlanTier.PRO,
                Subscription.status.in_(tuple(ENTITLED_STATUSES)),
            )
        )
        basic = int(total or 0) - int(pro or 0)
        return int(total or 0), int(live or 0), int(pro or 0), max(0, basic)

    async def owner_count(self) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.OWNER)
        )
        return int(result or 0)

    async def order_counts(self, since: datetime) -> tuple[int, int]:
        result = await self.session.execute(
            select(
                func.count(),
                func.count().filter(Order.status == OrderStatus.COMPLETED),
            ).where(Order.created_at >= since)
        )
        row = result.one()
        return int(row[0] or 0), int(row[1] or 0)

    async def revenue(self, since: datetime) -> Decimal:
        result = await self.session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.created_at >= since,
                Order.status.in_(REVENUE_STATUSES),
            )
        )
        return Decimal(result or 0)

    async def today_stats(self) -> tuple[int, Decimal]:
        since = self._today_start()
        orders = await self.session.scalar(
            select(func.count()).select_from(Order).where(Order.created_at >= since)
        )
        revenue = await self.session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.created_at >= since,
                Order.status.in_(REVENUE_STATUSES),
            )
        )
        return int(orders or 0), Decimal(revenue or 0)

    async def daily_series(self, since: datetime) -> list[tuple[date, int, Decimal]]:
        day = func.date(func.timezone("Asia/Kolkata", Order.created_at)).label("day")
        placed = func.count().label("placed")
        earned = func.coalesce(
            func.sum(Order.total).filter(Order.status.in_(REVENUE_STATUSES)),
            0,
        ).label("earned")
        result = await self.session.execute(
            select(day, placed, earned)
            .where(Order.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [(row[0], int(row[1] or 0), Decimal(row[2] or 0)) for row in result.all()]

    async def top_venues(
        self, since: datetime, limit: int = 15
    ) -> list[tuple[Restaurant, PlanTier | None, int, Decimal]]:
        revenue = func.coalesce(
            func.sum(Order.total).filter(Order.status.in_(REVENUE_STATUSES)),
            0,
        ).label("revenue")
        orders = func.count(Order.id).label("orders")
        result = await self.session.execute(
            select(Restaurant, Subscription.plan, orders, revenue)
            .join(Order, Order.restaurant_id == Restaurant.id)
            .outerjoin(Subscription, Subscription.restaurant_id == Restaurant.id)
            .where(Order.created_at >= since)
            .group_by(Restaurant.id, Subscription.plan)
            .order_by(revenue.desc(), orders.desc())
            .limit(limit)
        )
        rows: list[tuple[Restaurant, PlanTier | None, int, Decimal]] = []
        for row in result.all():
            plan = row[1]
            if plan is not None and not isinstance(plan, PlanTier):
                plan = PlanTier(plan)
            rows.append((row[0], plan, int(row[2] or 0), Decimal(row[3] or 0)))
        return rows
