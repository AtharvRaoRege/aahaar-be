from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.enums import PlanRequestStatus
from app.models.plan_request import PlanRequest
from app.repositories.base import BaseRepository


class PlanRequestRepository(BaseRepository[PlanRequest]):
    model = PlanRequest

    async def get_pending(self, restaurant_id: uuid.UUID) -> PlanRequest | None:
        result = await self.session.execute(
            select(PlanRequest).where(
                PlanRequest.restaurant_id == restaurant_id,
                PlanRequest.status == PlanRequestStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    async def list_pending(self) -> list[PlanRequest]:
        result = await self.session.execute(
            select(PlanRequest)
            .where(PlanRequest.status == PlanRequestStatus.PENDING)
            .order_by(PlanRequest.created_at.desc())
        )
        return list(result.scalars().all())
