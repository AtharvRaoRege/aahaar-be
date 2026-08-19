from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import PlanRequestStatus, PlanTier

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class PlanRequest(UUIDMixin, TimestampMixin, Base):
    """A cafe owner's request to move onto a paid plan."""

    __tablename__ = "plan_requests"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_plan: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier, native_enum=False, length=20),
        nullable=False,
    )
    status: Mapped[PlanRequestStatus] = mapped_column(
        SAEnum(PlanRequestStatus, native_enum=False, length=20),
        default=PlanRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    restaurant: Mapped[Restaurant] = relationship()
