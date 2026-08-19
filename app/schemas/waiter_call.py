from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import WaiterCallStatus
from app.schemas.common import CamelModel


class CreateWaiterCallRequest(CamelModel):
    table_number: str = Field(min_length=1, max_length=32)
    customer_session_id: uuid.UUID | None = None


class WaiterCallResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    table_number: str | None
    status: WaiterCallStatus
    created_at: datetime | None = None
    acknowledged_at: datetime | None = None
