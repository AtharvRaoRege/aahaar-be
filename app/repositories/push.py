from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.repositories.base import BaseRepository


class PushSubscriptionRepository(BaseRepository[PushSubscription]):
    model = PushSubscription

    async def list_for_restaurant(self, restaurant_id: uuid.UUID) -> list[PushSubscription]:
        result = await self.session.execute(
            select(PushSubscription).where(PushSubscription.restaurant_id == restaurant_id)
        )
        return list(result.scalars().all())

    async def get_for_user(
        self, user_id: uuid.UUID, restaurant_id: uuid.UUID, endpoint: str
    ) -> PushSubscription | None:
        result = await self.session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.restaurant_id == restaurant_id,
                PushSubscription.endpoint == endpoint,
            )
        )
        return result.scalar_one_or_none()

    async def delete_by_endpoint(self, user_id: uuid.UUID, endpoint: str) -> None:
        result = await self.session.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint == endpoint,
            )
        )
        for row in result.scalars().all():
            await self.delete(row)
