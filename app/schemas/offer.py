from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, model_validator

from app.models.enums import OfferKind, OfferState
from app.schemas.common import CamelModel, Money


class OfferBase(CamelModel):
    kind: OfferKind = OfferKind.PERCENT
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    terms: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=500)
    coupon_code: str | None = Field(default=None, max_length=32)
    value: Money | None = Field(default=None, ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = False
    sort_order: int = 0

    @model_validator(mode="after")
    def _check_window(self) -> OfferBase:
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("Offer end must be after its start.")
        if self.kind == OfferKind.PERCENT and self.value is not None and self.value > 100:
            raise ValueError("A percentage discount cannot exceed 100.")
        return self


class CreateOfferRequest(OfferBase):
    pass


class UpdateOfferRequest(CamelModel):
    kind: OfferKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    terms: str | None = Field(default=None, max_length=1000)
    image_url: str | None = Field(default=None, max_length=500)
    coupon_code: str | None = Field(default=None, max_length=32)
    value: Money | None = Field(default=None, ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class OfferResponse(OfferBase):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    state: OfferState


class PublicOfferResponse(CamelModel):
    id: uuid.UUID
    kind: OfferKind
    title: str
    description: str | None
    terms: str | None
    image_url: str | None
    coupon_code: str | None
    value: Money | None
    ends_at: datetime | None
