from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import VenueKind

if TYPE_CHECKING:
    from app.models.menu import Category, MenuItem
    from app.models.offer import Offer
    from app.models.order import Order
    from app.models.push_subscription import PushSubscription
    from app.models.qr_code import QrCode
    from app.models.review import Review
    from app.models.subscription import Subscription
    from app.models.tenant import Tenant


class Restaurant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "restaurants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    venue_kind: Mapped[VenueKind] = mapped_column(
        SAEnum(VenueKind, native_enum=False, length=20),
        default=VenueKind.RESTAURANT,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    primary_color: Mapped[str] = mapped_column(String(9), default="#FF5A36", nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(9), default="#FFC928", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maps_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    google_review_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    upi_vpa: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upi_payee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    waiter_call_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="restaurants")
    categories: Mapped[list[Category]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    menu_items: Mapped[list[MenuItem]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    orders: Mapped[list[Order]] = relationship(back_populates="restaurant")
    qr_codes: Mapped[list[QrCode]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    push_subscriptions: Mapped[list[PushSubscription]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    offers: Mapped[list[Offer]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan", uselist=False
    )
