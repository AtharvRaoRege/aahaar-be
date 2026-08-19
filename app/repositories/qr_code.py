from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.enums import QrKind
from app.models.qr_code import QrCode
from app.repositories.base import BaseRepository


class QrCodeRepository(BaseRepository[QrCode]):
    model = QrCode

    async def list_by_restaurant(self, restaurant_id: uuid.UUID) -> list[QrCode]:
        result = await self.session.execute(
            select(QrCode)
            .where(QrCode.restaurant_id == restaurant_id)
            .order_by(QrCode.kind.desc(), QrCode.created_at)
        )
        return list(result.scalars().all())

    async def count_tables(self, restaurant_id: uuid.UUID) -> int:
        """Table QRs only — the review QR does not consume plan quota."""
        result = await self.session.execute(
            select(func.count()).where(
                QrCode.restaurant_id == restaurant_id,
                QrCode.kind == QrKind.TABLE,
            )
        )
        return int(result.scalar_one() or 0)

    async def get_review_qr(self, restaurant_id: uuid.UUID) -> QrCode | None:
        result = await self.session.execute(
            select(QrCode).where(
                QrCode.restaurant_id == restaurant_id,
                QrCode.kind == QrKind.REVIEW,
            )
        )
        return result.scalar_one_or_none()
