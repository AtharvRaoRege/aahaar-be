from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import VenueKind
from app.schemas.auth import WaitlistUserResponse
from app.schemas.restaurant import RestaurantResponse


class AdminUserResponse(WaitlistUserResponse):
    restaurant_id: uuid.UUID | None = None
    restaurant_name: str | None = None
    venue_kind: VenueKind | None = None


class AdminRestaurantResponse(RestaurantResponse):
    owner_id: uuid.UUID | None = None
    owner_name: str | None = None
    owner_email: str | None = None
    created_at: datetime | None = None
