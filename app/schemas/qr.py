from __future__ import annotations

import uuid

from pydantic import Field

from app.models.enums import QrKind
from app.schemas.common import CamelModel


class CreateQrRequest(CamelModel):
    label: str = Field(min_length=1, max_length=120)
    table_number: str = Field(min_length=1, max_length=32)


class QrResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    label: str
    table_number: str | None
    target_url: str
    image_data_url: str
    kind: QrKind = QrKind.TABLE
