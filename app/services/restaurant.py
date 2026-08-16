from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.restaurant import Restaurant
from app.repositories.restaurant import RestaurantRepository
from app.schemas.restaurant import (
    CreateRestaurantRequest,
    UpdateRestaurantRequest,
)
from app.utils.slugs import random_suffix, slugify


class RestaurantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.restaurants = RestaurantRepository(session)

    async def list_for_tenant(self, tenant_id: uuid.UUID) -> list[Restaurant]:
        return await self.restaurants.list_by_tenant(tenant_id)

    async def get_owned(self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID) -> Restaurant:
        restaurant = await self.restaurants.get_for_tenant(restaurant_id, tenant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found.")
        return restaurant

    async def create(self, tenant_id: uuid.UUID, payload: CreateRestaurantRequest) -> Restaurant:
        slug = payload.slug or payload.name
        restaurant = Restaurant(
            tenant_id=tenant_id,
            name=payload.name,
            slug=await self._unique_slug(slug),
            description=payload.description,
            logo_url=payload.logo_url,
            cover_image_url=payload.cover_image_url,
            phone=payload.phone,
            address=payload.address,
            currency=payload.currency,
            timezone=payload.timezone,
            primary_color=payload.primary_color,
            secondary_color=payload.secondary_color,
            venue_kind=payload.venue_kind,
        )
        self.session.add(restaurant)
        await self.session.flush()
        from app.services.menu import MenuService

        await MenuService(self.session).ensure_default_categories(restaurant.id, commit=False)
        await self.session.commit()
        await self.session.refresh(restaurant)
        return restaurant

    async def update(
        self,
        restaurant_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: UpdateRestaurantRequest,
    ) -> Restaurant:
        restaurant = await self.get_owned(restaurant_id, tenant_id)
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(restaurant, field, value)
        await self.session.commit()
        await self.session.refresh(restaurant)
        return restaurant

    async def delete(self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        restaurant = await self.get_owned(restaurant_id, tenant_id)
        await self.session.delete(restaurant)
        await self.session.commit()

    async def get_public_by_slug(self, slug: str) -> Restaurant:
        restaurant = await self.restaurants.get_by_slug(slug)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found.")
        return restaurant

    async def _unique_slug(self, raw: str) -> str:
        base = slugify(raw)
        slug = base
        if not await self.restaurants.slug_exists(slug):
            return slug
        while await self.restaurants.slug_exists(slug):
            slug = f"{base}-{random_suffix()}"
        return slug


def get_restaurant_service(session: AsyncSession) -> RestaurantService:
    return RestaurantService(session)
