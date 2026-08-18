from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class CreateReviewRequest(CamelModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)
    improvement: str | None = Field(default=None, max_length=500)
    order_id: uuid.UUID | None = None


class ReviewResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    order_id: uuid.UUID | None
    rating: int
    comment: str | None
    improvement: str | None
    created_at: datetime


class ReviewSummaryResponse(CamelModel):
    average: float
    count: int
    distribution: dict[str, int]
