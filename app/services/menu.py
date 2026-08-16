from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.models.menu import Category, MenuItem, MenuItemAddon, MenuItemVariant
from app.repositories.menu import CategoryRepository, MenuItemRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.menu import (
    CreateCategoryRequest,
    CreateMenuItemRequest,
    MenuCategoryGroup,
    MenuItemResponse,
    MenuResponse,
    UpdateCategoryRequest,
    UpdateMenuItemRequest,
)

if TYPE_CHECKING:
    from app.services.menu_import import ImportRow

DEFAULT_CATEGORIES: tuple[tuple[str, int], ...] = (
    ("Starters", 0),
    ("Main Course", 1),
    ("Drinks", 2),
    ("Sweets", 3),
)


class MenuService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.categories = CategoryRepository(session)
        self.items = MenuItemRepository(session)
        self.restaurants = RestaurantRepository(session)

    # ── Menu view ────────────────────────────────────────────
    async def get_menu(self, restaurant_id: uuid.UUID, *, public: bool) -> MenuResponse:
        await self.ensure_default_categories(restaurant_id)
        categories = await self.categories.list_by_restaurant(restaurant_id, active_only=public)
        items = await self.items.list_by_restaurant(restaurant_id, available_only=public)

        by_category: dict[uuid.UUID | None, list[MenuItem]] = {}
        for item in items:
            by_category.setdefault(item.category_id, []).append(item)

        groups: list[MenuCategoryGroup] = []
        for category in categories:
            groups.append(
                MenuCategoryGroup(
                    id=category.id,
                    name=category.name,
                    sort_order=category.sort_order,
                    items=[
                        MenuItemResponse.model_validate(i) for i in by_category.get(category.id, [])
                    ],
                )
            )

        uncategorized = by_category.get(None, [])
        if uncategorized:
            groups.append(
                MenuCategoryGroup(
                    id=None,
                    name="Other",
                    sort_order=9999,
                    items=[MenuItemResponse.model_validate(i) for i in uncategorized],
                )
            )

        return MenuResponse(restaurant_id=restaurant_id, categories=groups)

    async def ensure_default_categories(
        self, restaurant_id: uuid.UUID, *, commit: bool = True
    ) -> None:
        existing = await self.categories.list_by_restaurant(restaurant_id)
        names = {category.name.strip().lower() for category in existing}
        added = False
        for name, sort_order in DEFAULT_CATEGORIES:
            if name.lower() in names:
                continue
            self.session.add(
                Category(
                    restaurant_id=restaurant_id,
                    name=name,
                    sort_order=sort_order,
                    is_active=True,
                )
            )
            added = True
        if added and commit:
            await self.session.commit()

    # ── Categories ───────────────────────────────────────────
    async def list_categories(self, restaurant_id: uuid.UUID) -> list[Category]:
        return await self.categories.list_by_restaurant(restaurant_id)

    async def create_category(
        self, restaurant_id: uuid.UUID, payload: CreateCategoryRequest
    ) -> Category:
        category = Category(
            restaurant_id=restaurant_id,
            name=payload.name,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        self.session.add(category)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def update_category(
        self,
        category_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: UpdateCategoryRequest,
        *,
        allow_cross_tenant: bool = False,
    ) -> Category:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("Category not found.")
        await self._assert_owns_restaurant(
            category.restaurant_id, tenant_id, allow_cross_tenant=allow_cross_tenant
        )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        await self.session.commit()
        await self.session.refresh(category)
        return category

    async def delete_category(
        self,
        category_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        allow_cross_tenant: bool = False,
    ) -> None:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("Category not found.")
        await self._assert_owns_restaurant(
            category.restaurant_id, tenant_id, allow_cross_tenant=allow_cross_tenant
        )
        await self.session.delete(category)
        await self.session.commit()

    # ── Menu items ───────────────────────────────────────────
    async def create_item(
        self,
        category_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: CreateMenuItemRequest,
        *,
        allow_cross_tenant: bool = False,
    ) -> MenuItem:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("Category not found.")
        await self._assert_owns_restaurant(
            category.restaurant_id, tenant_id, allow_cross_tenant=allow_cross_tenant
        )

        item = MenuItem(
            restaurant_id=category.restaurant_id,
            category_id=category.id,
            name=payload.name,
            description=payload.description,
            image_url=payload.image_url,
            base_price=payload.base_price,
            is_available=payload.is_available,
            is_vegetarian=payload.is_vegetarian,
            is_vegan=payload.is_vegan,
            spice_level=payload.spice_level,
            sort_order=payload.sort_order,
        )
        item.variants = [
            MenuItemVariant(
                name=v.name,
                price_delta=v.price_delta,
                is_default=v.is_default,
                sort_order=v.sort_order,
            )
            for v in payload.variants
        ]
        item.addons = [
            MenuItemAddon(
                name=a.name,
                price=a.price,
                is_available=a.is_available,
                sort_order=a.sort_order,
            )
            for a in payload.addons
        ]
        self.session.add(item)
        await self.session.commit()
        return await self._reload_item(item.id)

    async def update_item(
        self,
        item_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: UpdateMenuItemRequest,
        *,
        allow_cross_tenant: bool = False,
    ) -> MenuItem:
        item = await self.items.get_with_relations(item_id)
        if item is None:
            raise NotFoundError("Menu item not found.")
        await self._assert_owns_restaurant(
            item.restaurant_id, tenant_id, allow_cross_tenant=allow_cross_tenant
        )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        await self.session.commit()
        return await self._reload_item(item.id)

    async def delete_item(
        self,
        item_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        allow_cross_tenant: bool = False,
    ) -> None:
        item = await self.items.get(item_id)
        if item is None:
            raise NotFoundError("Menu item not found.")
        await self._assert_owns_restaurant(
            item.restaurant_id, tenant_id, allow_cross_tenant=allow_cross_tenant
        )
        await self.session.delete(item)
        await self.session.commit()

    async def import_dishes(
        self, restaurant_id: uuid.UUID, rows: list[ImportRow]
    ) -> tuple[int, int]:
        await self.ensure_default_categories(restaurant_id, commit=False)
        await self.session.flush()
        categories = await self.categories.list_by_restaurant(restaurant_id)
        by_name = {" ".join(category.name.split()).casefold(): category for category in categories}
        next_category_sort = max((category.sort_order for category in categories), default=-1)

        items = await self.items.list_by_restaurant(restaurant_id)
        existing = {(item.category_id, item.name.strip().lower()) for item in items}
        next_item_sort: dict[uuid.UUID, int] = {}
        for item in items:
            if item.category_id is None:
                continue
            next_item_sort[item.category_id] = max(
                next_item_sort.get(item.category_id, -1), item.sort_order
            )

        created = 0
        skipped = 0
        seen_in_file: set[tuple[uuid.UUID, str]] = set()

        for row in rows:
            key = " ".join(row.category.split()).casefold()
            category = by_name.get(key)
            if category is None:
                next_category_sort += 1
                category = Category(
                    restaurant_id=restaurant_id,
                    name=row.category.strip()[:120],
                    sort_order=next_category_sort,
                    is_active=True,
                )
                self.session.add(category)
                await self.session.flush()
                by_name[key] = category

            name_key = row.name.strip().lower()
            file_key = (category.id, name_key)
            if file_key in seen_in_file or (category.id, name_key) in existing:
                skipped += 1
                continue
            seen_in_file.add(file_key)

            sort_order = next_item_sort.get(category.id, -1) + 1
            next_item_sort[category.id] = sort_order
            self.session.add(
                MenuItem(
                    restaurant_id=restaurant_id,
                    category_id=category.id,
                    name=row.name.strip()[:160],
                    base_price=row.price,
                    is_available=True,
                    is_vegetarian=True,
                    sort_order=sort_order,
                )
            )
            existing.add(file_key)
            created += 1

        await self.session.commit()
        return created, skipped

    async def _reload_item(self, item_id: uuid.UUID) -> MenuItem:
        item = await self.items.get_with_relations(item_id)
        if item is None:
            raise NotFoundError("Menu item not found.")
        return item

    async def _assert_owns_restaurant(
        self,
        restaurant_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        allow_cross_tenant: bool = False,
    ) -> None:
        if allow_cross_tenant:
            restaurant = await self.restaurants.get(restaurant_id)
            if restaurant is None:
                raise NotFoundError("Restaurant not found.")
            return
        restaurant = await self.restaurants.get_for_tenant(restaurant_id, tenant_id)
        if restaurant is None:
            raise ForbiddenError("This resource belongs to another tenant.")


def get_menu_service(session: AsyncSession) -> MenuService:
    return MenuService(session)
