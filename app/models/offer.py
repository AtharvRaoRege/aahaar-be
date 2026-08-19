from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import OfferKind

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class Offer(UUIDMixin, TimestampMixin, Base):
    """A promotion shown on the customer menu.

    Display-only by design (PRD §17): the coupon code is surfaced to the diner
    and to staff, but no discount is applied to the order total in v1.
    """

    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint("value is null or value >= 0", name="ck_offers_value_nonneg"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[OfferKind] = mapped_column(
        SAEnum(OfferKind, native_enum=False, length=20),
        default=OfferKind.PERCENT,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coupon_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    restaurant: Mapped[Restaurant] = relationship(back_populates="offers")
