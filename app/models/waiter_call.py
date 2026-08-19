from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import WaiterCallStatus

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class WaiterCall(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "waiter_calls"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customer_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[WaiterCallStatus] = mapped_column(
        SAEnum(WaiterCallStatus, native_enum=False, length=20),
        default=WaiterCallStatus.PENDING,
        nullable=False,
        index=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    restaurant: Mapped[Restaurant] = relationship()
