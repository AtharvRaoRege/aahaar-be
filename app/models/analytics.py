from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDMixin
from app.models.enums import AnalyticsEventType


class AnalyticsEvent(UUIDMixin, Base):
    """Append-only engagement log. Never updated, only inserted and aggregated."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index(
            "ix_analytics_restaurant_type_time",
            "restaurant_id",
            "event_type",
            "created_at",
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[AnalyticsEventType] = mapped_column(
        SAEnum(AnalyticsEventType, native_enum=False, length=24), nullable=False
    )
    customer_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer_sessions.id", ondelete="SET NULL"), nullable=True
    )
    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    visitor_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
