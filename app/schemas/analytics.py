from __future__ import annotations

import uuid
from datetime import date

from pydantic import Field

from app.models.enums import AnalyticsEventType
from app.schemas.common import CamelModel, Money


class LogEventRequest(CamelModel):
    event_type: AnalyticsEventType
    customer_session_id: uuid.UUID | None = None
    table_number: str | None = Field(default=None, max_length=32)
    visitor_key: str | None = Field(default=None, max_length=64)
    target_id: uuid.UUID | None = None
    meta: dict | None = None


class NamedCount(CamelModel):
    id: uuid.UUID | None = None
    label: str
    count: int


class DayPoint(CamelModel):
    day: date
    count: int


class HourPoint(CamelModel):
    hour: int
    count: int


class CommissionSavings(CamelModel):
    """What the same direct orders would have cost through an aggregator."""

    direct_order_revenue: Money
    commission_rate: float
    commission_avoided: Money
    platform_cost: Money
    net_saving: Money
    order_count: int


class UpsellImpact(CamelModel):
    accepted_count: int
    attributed_revenue: Money


class DishRow(CamelModel):
    """How one dish performed, ranked on what it actually sold."""

    menu_item_id: uuid.UUID
    name: str
    category: str | None
    price: Money
    units_sold: int
    revenue: Money
    share_of_orders: float
    verdict: str


class AnalyticsSummary(CamelModel):
    range_days: int
    plan: str
    is_pro: bool

    # Available on every plan.
    qr_scans: int
    menu_views: int
    orders_placed: int
    orders_completed: int
    popular_categories: list[NamedCount]

    # Pro only — empty/None for Basic.
    unique_visitors: int | None = None
    repeat_visitors: int | None = None
    average_order_value: Money | None = None
    total_revenue: Money | None = None
    top_viewed_items: list[NamedCount] = Field(default_factory=list)
    top_ordered_items: list[NamedCount] = Field(default_factory=list)
    table_scans: list[NamedCount] = Field(default_factory=list)
    offer_views: list[NamedCount] = Field(default_factory=list)
    peak_hours: list[HourPoint] = Field(default_factory=list)
    scans_by_day: list[DayPoint] = Field(default_factory=list)
    commission_savings: CommissionSavings | None = None
    upsell_impact: UpsellImpact | None = None


class DishPerformanceResponse(CamelModel):
    range_days: int
    top: list[DishRow]
    slow: list[DishRow]
    total_units: int
