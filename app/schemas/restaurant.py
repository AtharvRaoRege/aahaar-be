from __future__ import annotations

import uuid

from pydantic import Field

from app.models.enums import VenueKind
from app.schemas.common import CamelModel


class RestaurantBase(CamelModel):
    name: str = Field(min_length=1, max_length=160)
    venue_kind: VenueKind = VenueKind.RESTAURANT
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    cover_image_url: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None
    currency: str = Field(default="INR", max_length=8)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    primary_color: str = Field(default="#FF5A36", max_length=9)
    secondary_color: str = Field(default="#FFC928", max_length=9)


class CreateRestaurantRequest(RestaurantBase):
    slug: str | None = Field(default=None, min_length=1, max_length=160)


class UpdateRestaurantRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    venue_kind: VenueKind | None = None
    description: str | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    cover_image_url: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = None
    currency: str | None = Field(default=None, max_length=8)
    timezone: str | None = Field(default=None, max_length=64)
    primary_color: str | None = Field(default=None, max_length=9)
    secondary_color: str | None = Field(default=None, max_length=9)
    is_active: bool | None = None


class RestaurantResponse(RestaurantBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    is_active: bool


class PublicRestaurantResponse(CamelModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    cover_image_url: str | None
    phone: str | None
    address: str | None
    currency: str
    primary_color: str
    secondary_color: str
