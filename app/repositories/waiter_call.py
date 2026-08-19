from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.enums import WaiterCallStatus
from app.models.waiter_call import WaiterCall
from app.repositories.base import BaseRepository


class WaiterCallRepository(BaseRepository[WaiterCall]):
    model = WaiterCall

    async def get_pending_for_table(
        self, restaurant_id: uuid.UUID, table_number: str
    ) -> WaiterCall | None:
        result = await self.session.execute(
            select(WaiterCall).where(
                WaiterCall.restaurant_id == restaurant_id,
                WaiterCall.table_number == table_number,
                WaiterCall.status == WaiterCallStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending(self, restaurant_id: uuid.UUID) -> list[WaiterCall]:
        result = await self.session.execute(
            select(WaiterCall)
            .where(
                WaiterCall.restaurant_id == restaurant_id,
                WaiterCall.status == WaiterCallStatus.PENDING,
            )
            .order_by(WaiterCall.created_at.desc())
        )
        return list(result.scalars().all())
