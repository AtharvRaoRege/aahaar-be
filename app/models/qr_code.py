from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class QrCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "qr_codes"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    table_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_url: Mapped[str] = mapped_column(String(600), nullable=False)
    image_data_url: Mapped[str] = mapped_column(Text, nullable=False)

    restaurant: Mapped[Restaurant] = relationship(back_populates="qr_codes")
