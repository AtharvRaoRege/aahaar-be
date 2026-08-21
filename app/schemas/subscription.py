from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import PlanTier, SubscriptionStatus
from app.schemas.common import CamelModel, Money


class PlanSpecResponse(CamelModel):
    tier: PlanTier
    monthly_price: Money
    trial_days: int
    table_limit: int | None
    features: list[str]
    includes: list[str]


class SubscriptionResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    plan: PlanTier
    effective_plan: PlanTier
    status: SubscriptionStatus
    monthly_price: Money
    trial_ends_at: datetime | None
    current_period_end: datetime | None
    grace_ends_at: datetime | None
    pro_trial_used: bool
    scheduled_plan: PlanTier | None
    cancel_at_period_end: bool
    cancel_reason: str | None
    has_payment_method: bool
    days_left: int | None
    table_limit: int | None
    features: list[str]
    pending_plan: PlanTier | None = None
    pending_request_id: uuid.UUID | None = None
    menu_scan_enabled: bool = False


class ChangePlanRequest(CamelModel):
    plan: PlanTier


class CancelSubscriptionRequest(CamelModel):
    reason: str | None = Field(default=None, max_length=500)


class AddPaymentMethodRequest(CamelModel):
    """Placeholder until a PCI-compliant provider is wired in (PRD §34).

    Only an opaque provider reference is ever accepted — no card data reaches
    this API.
    """

    provider_ref: str = Field(min_length=3, max_length=120)
