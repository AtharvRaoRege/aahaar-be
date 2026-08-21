from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, status

from app.dependencies.auth import CurrentUser
from app.dependencies.db import DBSession
from app.dependencies.rate_limit import rate_limit
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import OrderStatus
from app.schemas.common import Page, PageParams
from app.schemas.order import (
    AdvanceOrderRequest,
    CreateOrderRequest,
    OrderResponse,
    OrderStageCounts,
    RejectOrderRequest,
    UpdateOrderStatusRequest,
)
from app.schemas.waiter_call import WaiterCallResponse
from app.services.order import OrderService
from app.services.waiter_call import WaiterCallService

router = APIRouter(tags=["orders"])


# ── Public: place & track ────────────────────────────────────
@router.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: CreateOrderRequest,
    db: DBSession,
    background: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _: None = Depends(rate_limit("order")),
) -> OrderResponse:
    return await OrderService(db).create_order(payload, idempotency_key, background=background)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: uuid.UUID, db: DBSession) -> OrderResponse:
    return await OrderService(db).get_public_order(order_id)


# ── Dashboard: list ──────────────────────────────────────────
@router.get("/restaurants/{restaurant_id}/orders", response_model=Page[OrderResponse])
async def list_restaurant_orders(
    restaurant: OwnedRestaurant,
    db: DBSession,
    status_filter: list[OrderStatus] | None = Query(default=None, alias="status"),
    active: bool = Query(default=False),
    table_number: str | None = Query(default=None, alias="tableNumber", max_length=32),
    search: str | None = Query(default=None, max_length=120),
    since_hours: int | None = Query(default=None, ge=1, le=8760, alias="sinceHours"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
) -> Page[OrderResponse]:
    params = PageParams(page=page, page_size=page_size)
    return await OrderService(db).list_orders(
        restaurant.id,
        statuses=status_filter,
        active_only=active,
        params=params,
        table_number=table_number,
        search=search,
        since_hours=since_hours,
    )


@router.get(
    "/restaurants/{restaurant_id}/orders/counts",
    response_model=OrderStageCounts,
)
async def count_restaurant_orders(
    restaurant: OwnedRestaurant,
    db: DBSession,
    table_number: str | None = Query(default=None, alias="tableNumber", max_length=32),
    search: str | None = Query(default=None, max_length=120),
    since_hours: int | None = Query(default=None, ge=1, le=8760, alias="sinceHours"),
) -> OrderStageCounts:
    return await OrderService(db).stage_counts(
        restaurant.id,
        table_number=table_number,
        search=search,
        since_hours=since_hours,
    )


# ── Dashboard: staff transitions ─────────────────────────────
@router.post("/orders/{order_id}/accept", response_model=OrderResponse)
async def accept_order(order_id: uuid.UUID, db: DBSession, user: CurrentUser) -> OrderResponse:
    return await OrderService(db).accept_order(
        order_id, user.tenant_id, user.id, allow_cross_tenant=user.is_super_admin
    )


@router.post("/orders/{order_id}/reject", response_model=OrderResponse)
async def reject_order(
    order_id: uuid.UUID,
    payload: RejectOrderRequest,
    db: DBSession,
    user: CurrentUser,
) -> OrderResponse:
    return await OrderService(db).reject_order(
        order_id,
        user.tenant_id,
        user.id,
        payload.note,
        allow_cross_tenant=user.is_super_admin,
    )


@router.patch("/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    payload: UpdateOrderStatusRequest,
    db: DBSession,
    user: CurrentUser,
) -> OrderResponse:
    return await OrderService(db).update_status(
        order_id,
        user.tenant_id,
        user.id,
        payload.status,
        payload.note,
        allow_cross_tenant=user.is_super_admin,
    )


@router.post("/orders/{order_id}/advance", response_model=OrderResponse)
async def advance_order(
    order_id: uuid.UUID,
    payload: AdvanceOrderRequest,
    db: DBSession,
    user: CurrentUser,
) -> OrderResponse:
    """Advance an order to a later stage in one tap, recording every hop."""
    return await OrderService(db).advance_to(
        order_id,
        user.tenant_id,
        user.id,
        payload.target,
        allow_cross_tenant=user.is_super_admin,
    )


@router.get(
    "/restaurants/{restaurant_id}/waiter-calls",
    response_model=list[WaiterCallResponse],
)
async def list_waiter_calls(
    restaurant: OwnedRestaurant,
    db: DBSession,
) -> list[WaiterCallResponse]:
    return await WaiterCallService(db).list_pending(restaurant.id)


@router.post(
    "/restaurants/{restaurant_id}/waiter-calls/{call_id}/ack",
    response_model=WaiterCallResponse,
)
async def ack_waiter_call(
    call_id: uuid.UUID,
    restaurant: OwnedRestaurant,
    db: DBSession,
) -> WaiterCallResponse:
    return await WaiterCallService(db).acknowledge(restaurant.id, call_id)
