from __future__ import annotations

import uuid

from pydantic import Field

from app.models.enums import VenueKind
from app.schemas.common import CamelModel


class DayHours(CamelModel):
    """One day's service window. ``closed`` wins over the times."""

    closed: bool = False
    opens: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    closes: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


OpeningHours = dict[str, DayHours]


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
    maps_url: str | None = Field(default=None, max_length=500)
    google_review_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    upi_vpa: str | None = Field(default=None, max_length=120)
    upi_payee_name: str | None = Field(default=None, max_length=120)
    opening_hours: OpeningHours | None = None
    waiter_call_enabled: bool = False


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
    maps_url: str | None = Field(default=None, max_length=500)
    google_review_url: str | None = Field(default=None, max_length=500)
    instagram_url: str | None = Field(default=None, max_length=500)
    upi_vpa: str | None = Field(default=None, max_length=120)
    upi_payee_name: str | None = Field(default=None, max_length=120)
    opening_hours: OpeningHours | None = None
    is_active: bool | None = None
    is_published: bool | None = None
    waiter_call_enabled: bool | None = None


class RestaurantResponse(RestaurantBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    slug: str
    is_active: bool
    is_published: bool


class PublishRestaurantRequest(CamelModel):
    is_published: bool


class PublishReadinessResponse(CamelModel):
    """Setup suggestions. Advisory only — going live is never blocked by these."""

    is_complete: bool
    is_published: bool
    has_logo: bool
    has_address: bool
    has_phone: bool
    has_category: bool
    has_menu_item: bool
    has_table_qr: bool
    blockers: list[str]


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
    maps_url: str | None = None
    google_review_url: str | None = None
    instagram_url: str | None = None
    upi_vpa: str | None = None
    upi_payee_name: str | None = None
    opening_hours: OpeningHours | None = None
    is_serving: bool = True
    unavailable_reason: str | None = None
    waiter_call_enabled: bool = False
