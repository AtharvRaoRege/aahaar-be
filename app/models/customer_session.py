from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDMixin

if TYPE_CHECKING:
    from app.models.order import Order


class CustomerSession(UUIDMixin, Base):
    __tablename__ = "customer_sessions"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    guest_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    room_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="customer_session")
