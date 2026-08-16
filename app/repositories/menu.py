from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.menu import Category, MenuItem
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def list_by_restaurant(
        self, restaurant_id: uuid.UUID, *, active_only: bool = False
    ) -> list[Category]:
        stmt = select(Category).where(Category.restaurant_id == restaurant_id)
        if active_only:
            stmt = stmt.where(Category.is_active.is_(True))
        stmt = stmt.order_by(Category.sort_order, Category.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MenuItemRepository(BaseRepository[MenuItem]):
    model = MenuItem

    async def get_with_relations(self, item_id: uuid.UUID) -> MenuItem | None:
        result = await self.session.execute(
            select(MenuItem)
            .where(MenuItem.id == item_id)
            .options(selectinload(MenuItem.variants), selectinload(MenuItem.addons))
        )
        return result.scalar_one_or_none()

    async def list_by_restaurant(
        self, restaurant_id: uuid.UUID, *, available_only: bool = False
    ) -> list[MenuItem]:
        stmt = (
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant_id)
            .options(selectinload(MenuItem.variants), selectinload(MenuItem.addons))
            .order_by(MenuItem.sort_order, MenuItem.name)
        )
        if available_only:
            stmt = stmt.where(MenuItem.is_available.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids(
        self, item_ids: Sequence[uuid.UUID], restaurant_id: uuid.UUID
    ) -> list[MenuItem]:
        if not item_ids:
            return []
        result = await self.session.execute(
            select(MenuItem)
            .where(
                MenuItem.id.in_(list(item_ids)),
                MenuItem.restaurant_id == restaurant_id,
            )
            .options(selectinload(MenuItem.variants), selectinload(MenuItem.addons))
        )
        return list(result.scalars().all())
