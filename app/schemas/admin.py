from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import PlanRequestStatus, PlanTier, SubscriptionStatus, VenueKind
from app.schemas.auth import WaitlistUserResponse
from app.schemas.common import CamelModel
from app.schemas.restaurant import RestaurantResponse


class AdminUserResponse(WaitlistUserResponse):
    restaurant_id: uuid.UUID | None = None
    restaurant_name: str | None = None
    venue_kind: VenueKind | None = None


class AdminRestaurantResponse(RestaurantResponse):
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    created_at: datetime | None = None
    plan: PlanTier | None = None
    subscription_status: SubscriptionStatus | None = None
    trial_ends_at: datetime | None = None
    current_period_end: datetime | None = None


class PlanRequestResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    restaurant_name: str
    requested_plan: PlanTier
    status: PlanRequestStatus
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    created_at: datetime | None = None


class SetActiveRequest(CamelModel):
    is_active: bool


class SetPublishedRequest(CamelModel):
    is_published: bool


class AssignPlanRequest(CamelModel):
    plan: PlanTier


class PlatformSettingsResponse(CamelModel):
    open_registration: bool


class UpdatePlatformSettingsRequest(CamelModel):
    open_registration: bool


class AdminDailyPoint(CamelModel):
    day: date
    orders: int
    revenue: Decimal


class AdminTopVenue(CamelModel):
    restaurant_id: uuid.UUID
    name: str
    venue_kind: VenueKind
    plan: PlanTier | None = None
    is_published: bool
    orders: int
    revenue: Decimal


class AdminAnalyticsTotals(CamelModel):
    orders_placed: int
    orders_completed: int
    revenue: Decimal
    revenue_today: Decimal
    orders_today: int
    venues_total: int
    venues_live: int
    venues_pro: int
    venues_basic: int
    owners_total: int


class AdminAnalyticsResponse(CamelModel):
    range_days: int
    totals: AdminAnalyticsTotals
    daily: list[AdminDailyPoint]
    top_venues: list[AdminTopVenue]
