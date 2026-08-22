from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.restaurant import Restaurant
from app.repositories.menu import CategoryRepository, MenuItemRepository
from app.repositories.qr_code import QrCodeRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.restaurant import (
    CreateRestaurantRequest,
    PublishReadinessResponse,
    UpdateRestaurantRequest,
)
from app.utils.slugs import random_suffix, slugify


class RestaurantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.restaurants = RestaurantRepository(session)
        self.categories = CategoryRepository(session)
        self.items = MenuItemRepository(session)
        self.qr_codes = QrCodeRepository(session)

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
            maps_url=payload.maps_url,
            google_review_url=payload.google_review_url,
            instagram_url=payload.instagram_url,
            upi_vpa=payload.upi_vpa,
            upi_payee_name=payload.upi_payee_name,
            opening_hours=self._dump_hours(payload.opening_hours),
        )
        self.session.add(restaurant)
        await self.session.flush()
        from app.services.menu import MenuService
        from app.services.subscription import SubscriptionService

        await MenuService(self.session).ensure_default_categories(restaurant.id, commit=False)
        # Every new venue starts on a Basic trial (PRD §8).
        await SubscriptionService(self.session).get_or_create(restaurant.id, commit=False)
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

    async def set_logo_url(self, restaurant_id: uuid.UUID, url: str) -> Restaurant:
        """Point the venue at a freshly uploaded logo."""
        restaurant = await self.restaurants.get(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found.")
        restaurant.logo_url = url
        await self.session.commit()
        await self.session.refresh(restaurant)
        return restaurant

    async def publish(self, restaurant: Restaurant, is_published: bool) -> Restaurant:
        """Flip the public menu on or off.

        The readiness checklist is advice, never a gate: an owner who wants their
        menu live tonight without a logo is making a reasonable call, and the one
        thing that must never happen is a scanned QR with no menu behind it.
        """
        restaurant.is_published = is_published
        await self.session.commit()
        await self.session.refresh(restaurant)
        return restaurant

    async def publish_readiness(self, restaurant: Restaurant) -> PublishReadinessResponse:
        categories = await self.categories.list_by_restaurant(restaurant.id)
        items = await self.items.list_by_restaurant(restaurant.id)
        table_qr_count = await self.qr_codes.count_tables(restaurant.id)

        checks = {
            "logo": bool(restaurant.logo_url),
            "address": bool((restaurant.address or "").strip()),
            "phone": bool((restaurant.phone or "").strip()),
            "category": any(category.is_active for category in categories),
            "menuItem": len(items) > 0,
            "tableQr": table_qr_count > 0,
        }
        blockers = [name for name, ok in checks.items() if not ok]
        return PublishReadinessResponse(
            is_complete=not blockers,
            is_published=restaurant.is_published,
            has_logo=checks["logo"],
            has_address=checks["address"],
            has_phone=checks["phone"],
            has_category=checks["category"],
            has_menu_item=checks["menuItem"],
            has_table_qr=checks["tableQr"],
            blockers=blockers,
        )

    def _dump_hours(self, hours: object | None) -> dict | None:
        if hours is None:
            return None
        return {
            day: value.model_dump() if hasattr(value, "model_dump") else value
            for day, value in hours.items()  # type: ignore[union-attr]
        }

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
