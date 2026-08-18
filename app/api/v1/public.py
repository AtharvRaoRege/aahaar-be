from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.dependencies.db import DBSession
from app.dependencies.rate_limit import rate_limit
from app.dependencies.restaurant import PublicRestaurant
from app.schemas.customer import (
    CreateCustomerSessionRequest,
    CustomerSessionResponse,
)
from app.schemas.menu import MenuResponse
from app.schemas.order import OrderResponse
from app.schemas.restaurant import PublicRestaurantResponse
from app.services.customer import CustomerService
from app.services.menu import MenuService
from app.services.order import OrderService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/restaurants/{slug}", response_model=PublicRestaurantResponse)
async def get_public_restaurant_profile(
    restaurant: PublicRestaurant,
) -> PublicRestaurantResponse:
    return PublicRestaurantResponse.model_validate(restaurant)


@router.get("/restaurants/{slug}/menu", response_model=MenuResponse)
async def get_public_menu(restaurant: PublicRestaurant, db: DBSession) -> MenuResponse:
    return await MenuService(db).get_menu(restaurant.id, public=True)


@router.post(
    "/customer-sessions",
    response_model=CustomerSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_session(
    payload: CreateCustomerSessionRequest,
    db: DBSession,
    _: None = Depends(rate_limit("public")),
) -> CustomerSessionResponse:
    session = await CustomerService(db).create_session(payload)
    return CustomerSessionResponse.model_validate(session)


@router.get("/customer-sessions/{session_id}", response_model=CustomerSessionResponse)
async def get_customer_session(session_id: uuid.UUID, db: DBSession) -> CustomerSessionResponse:
    session = await CustomerService(db).get_session(session_id)
    return CustomerSessionResponse.model_validate(session)


@router.get(
    "/customer-sessions/{session_id}/open-order",
    response_model=OrderResponse,
    responses={204: {"description": "No open order for this table"}},
)
async def get_open_order_for_session(
    session_id: uuid.UUID,
    db: DBSession,
) -> OrderResponse | Response:
    order = await OrderService(db).get_open_for_session(session_id)
    if order is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return order
