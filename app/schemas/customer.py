from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class CreateCustomerSessionRequest(CamelModel):
    restaurant_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, max_length=160)
    name: str | None = Field(default=None, max_length=120)
    contact_number: str | None = Field(default=None, max_length=32)
    guest_count: int = Field(default=1, ge=1, le=100)
    table_number: str = Field(min_length=1, max_length=32)
    room_number: str | None = Field(default=None, max_length=32)


class CustomerSessionResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    name: str
    contact_number: str | None
    guest_count: int
    table_number: str | None
    room_number: str | None
    created_at: datetime
    expires_at: datetime
