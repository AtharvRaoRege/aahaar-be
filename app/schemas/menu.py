from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import Field

from app.schemas.common import CamelModel, Money


# ── Variants ──────────────────────────────────────────────────
class VariantBase(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    price_delta: Decimal = Field(default=Decimal("0"))
    is_default: bool = False
    sort_order: int = 0


class CreateVariantRequest(VariantBase):
    pass


class VariantResponse(CamelModel):
    id: uuid.UUID
    name: str
    price_delta: Money
    is_default: bool
    sort_order: int


# ── Addons ────────────────────────────────────────────────────
class AddonBase(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    is_available: bool = True
    sort_order: int = 0


class CreateAddonRequest(AddonBase):
    pass


class AddonResponse(CamelModel):
    id: uuid.UUID
    name: str
    price: Money
    is_available: bool
    sort_order: int


# ── Categories ────────────────────────────────────────────────
class CreateCategoryRequest(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    is_active: bool = True


class UpdateCategoryRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    sort_order: int
    is_active: bool


# ── Menu items ────────────────────────────────────────────────
class CreateMenuItemRequest(CamelModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    base_price: Decimal = Field(ge=0)
    category_id: uuid.UUID | None = None
    is_available: bool = True
    is_vegetarian: bool = True
    is_vegan: bool = False
    spice_level: int = Field(default=0, ge=0, le=3)
    sort_order: int = 0
    variants: list[CreateVariantRequest] = Field(default_factory=list)
    addons: list[CreateAddonRequest] = Field(default_factory=list)


class UpdateMenuItemRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    base_price: Decimal | None = Field(default=None, ge=0)
    category_id: uuid.UUID | None = None
    is_available: bool | None = None
    is_vegetarian: bool | None = None
    is_vegan: bool | None = None
    spice_level: int | None = Field(default=None, ge=0, le=3)
    sort_order: int | None = None


class MenuItemResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    description: str | None
    image_url: str | None
    base_price: Money
    is_available: bool
    is_vegetarian: bool
    is_vegan: bool
    spice_level: int
    sort_order: int
    variants: list[VariantResponse] = Field(default_factory=list)
    addons: list[AddonResponse] = Field(default_factory=list)


class MenuCategoryGroup(CamelModel):
    """A category together with its available items — used by the menu view."""

    id: uuid.UUID | None
    name: str
    sort_order: int
    items: list[MenuItemResponse]


class MenuResponse(CamelModel):
    restaurant_id: uuid.UUID
    categories: list[MenuCategoryGroup]


class ImportJobResponse(CamelModel):
    job_id: uuid.UUID
    status: str
    created: int = 0
    skipped: int = 0
    error: str | None = None
