from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import ENTITLED_STATUSES, PlanTier, SubscriptionStatus

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class Subscription(UUIDMixin, TimestampMixin, Base):
    """One subscription per venue — each kitchen pays for its own plan."""

    __tablename__ = "subscriptions"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier, native_enum=False, length=20),
        default=PlanTier.BASIC,
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, native_enum=False, length=20),
        default=SubscriptionStatus.TRIALING,
        nullable=False,
        index=True,
    )
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pro_trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_plan: Mapped[PlanTier | None] = mapped_column(
        SAEnum(PlanTier, native_enum=False, length=20), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)

    restaurant: Mapped[Restaurant] = relationship(back_populates="subscription")

    @property
    def is_entitled(self) -> bool:
        """True while the venue may still use its plan's paid feature set."""
        return self.status in ENTITLED_STATUSES

    @property
    def effective_plan(self) -> PlanTier:
        """Plan actually in force — a lapsed venue falls back to Basic."""
        return self.plan if self.is_entitled else PlanTier.BASIC
