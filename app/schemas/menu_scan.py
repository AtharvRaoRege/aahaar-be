from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel, Money

Confidence = Literal["HIGH", "MEDIUM", "LOW"]


class MenuScanRow(CamelModel):
    """One dish read off the menu, pending the owner's approval."""

    name: str = Field(max_length=160)
    category: str = Field(max_length=120)
    price: Money | None = None
    description: str | None = Field(default=None, max_length=1000)
    is_vegetarian: bool | None = None
    confidence: Confidence = "MEDIUM"


class MenuScanResponse(CamelModel):
    rows: list[MenuScanRow]
    image_quality: Literal["GOOD", "POOR"]
    notes: str | None
    low_confidence_count: int
    truncated: bool


class ApplyMenuScanRequest(CamelModel):
    """The rows the owner approved. Only these are written to the menu."""

    rows: list[MenuScanRow] = Field(min_length=1, max_length=300)


class ApplyMenuScanResponse(CamelModel):
    created: int
    skipped: int


class MenuScanJobResponse(CamelModel):
    """Background scan job — poll until done, then review rows before apply."""

    job_id: uuid.UUID
    status: Literal["pending", "running", "done", "failed"]
    error: str | None = None
    result: MenuScanResponse | None = None
