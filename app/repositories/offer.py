from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select

from app.models.offer import Offer
from app.repositories.base import BaseRepository


class OfferRepository(BaseRepository[Offer]):
    model = Offer

    async def list_by_restaurant(self, restaurant_id: uuid.UUID) -> list[Offer]:
        result = await self.session.execute(
            select(Offer)
            .where(Offer.restaurant_id == restaurant_id)
            .order_by(Offer.sort_order, Offer.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_live(self, restaurant_id: uuid.UUID, now: datetime) -> list[Offer]:
        """Active offers whose window currently includes ``now``."""
        result = await self.session.execute(
            select(Offer)
            .where(
                Offer.restaurant_id == restaurant_id,
                Offer.is_active.is_(True),
                or_(Offer.starts_at.is_(None), Offer.starts_at <= now),
                or_(Offer.ends_at.is_(None), Offer.ends_at > now),
            )
            .order_by(Offer.sort_order, Offer.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_restaurant(
        self, offer_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> Offer | None:
        result = await self.session.execute(
            select(Offer).where(Offer.id == offer_id, Offer.restaurant_id == restaurant_id)
        )
        return result.scalar_one_or_none()
