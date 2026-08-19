from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import OrderStatus
from app.schemas.common import CamelModel, Money


class OrderItemRequest(CamelModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(ge=1, le=100)
    variant_id: uuid.UUID | None = None
    addon_ids: list[uuid.UUID] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=300)


class CreateOrderRequest(CamelModel):
    restaurant_id: uuid.UUID
    customer_session_id: uuid.UUID
    items: list[OrderItemRequest] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=500)


class UpdateOrderStatusRequest(CamelModel):
    status: OrderStatus
    note: str | None = Field(default=None, max_length=300)


class AdvanceOrderRequest(CamelModel):
    """Target stage for a single staff tap. The server walks the valid path."""

    target: OrderStatus


class RejectOrderRequest(CamelModel):
    note: str | None = Field(default=None, max_length=300)


class OrderStageCounts(CamelModel):
    """Exact ticket totals per working stage, for the orders screen tabs."""

    new: int = 0
    cooking: int = 0
    ready: int = 0
    closed: int = 0
    all: int = 0


class OrderItemResponse(CamelModel):
    id: uuid.UUID
    menu_item_id: uuid.UUID | None
    name_snapshot: str
    price_snapshot: Money
    quantity: int
    variant_snapshot: dict | None
    addon_snapshot: list | None
    notes: str | None
    subtotal: Money


class OrderStatusHistoryResponse(CamelModel):
    id: uuid.UUID
    old_status: OrderStatus | None
    new_status: OrderStatus
    changed_by: uuid.UUID | None
    note: str | None
    created_at: datetime


class OrderCustomerInfo(CamelModel):
    name: str
    contact_number: str | None
    guest_count: int


class OrderResponse(CamelModel):
    id: uuid.UUID
    restaurant_id: uuid.UUID
    customer_session_id: uuid.UUID | None
    order_number: int
    status: OrderStatus
    subtotal: Money
    discount: Money
    tax: Money
    total: Money
    table_number: str | None
    room_number: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    customer: OrderCustomerInfo | None = None
    reviewed: bool = False
    items: list[OrderItemResponse] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryResponse] = Field(default_factory=list)
