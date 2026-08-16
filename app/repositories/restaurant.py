from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.restaurant import Restaurant
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository[Tenant]):
    model = Tenant

    async def get_by_slug(self, slug: str) -> Tenant | None:
        result = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()


class RestaurantRepository(BaseRepository[Restaurant]):
    model = Restaurant

    async def get_by_slug(self, slug: str) -> Restaurant | None:
        result = await self.session.execute(select(Restaurant).where(Restaurant.slug == slug))
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        result = await self.session.execute(select(Restaurant.id).where(Restaurant.slug == slug))
        return result.first() is not None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Restaurant]:
        result = await self.session.execute(
            select(Restaurant)
            .where(Restaurant.tenant_id == tenant_id)
            .order_by(Restaurant.created_at)
        )
        return list(result.scalars().all())

    async def get_for_tenant(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Restaurant | None:
        result = await self.session.execute(
            select(Restaurant).where(
                Restaurant.id == restaurant_id, Restaurant.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Restaurant]:
        result = await self.session.execute(
            select(Restaurant).order_by(Restaurant.created_at.desc())
        )
        return list(result.scalars().all())
