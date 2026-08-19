from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.enums import SubscriptionStatus
from app.models.subscription import Subscription
from app.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription

    async def get_for_restaurant(self, restaurant_id: uuid.UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription).where(Subscription.restaurant_id == restaurant_id)
        )
        return result.scalar_one_or_none()

    async def list_for_restaurants(self, restaurant_ids: Sequence[uuid.UUID]) -> list[Subscription]:
        if not restaurant_ids:
            return []
        result = await self.session.execute(
            select(Subscription).where(Subscription.restaurant_id.in_(list(restaurant_ids)))
        )
        return list(result.scalars().all())

    async def list_by_statuses(self, statuses: Sequence[SubscriptionStatus]) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription).where(Subscription.status.in_(list(statuses)))
        )
        return list(result.scalars().all())
