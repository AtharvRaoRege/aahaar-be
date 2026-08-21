from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.dependencies.db import DBSession
from app.dependencies.rate_limit import rate_limit
from app.dependencies.restaurant import PublicRestaurant, ServingRestaurant
from app.schemas.analytics import LogEventRequest
from app.schemas.common import Message
from app.schemas.customer import (
    CreateCustomerSessionRequest,
    CustomerSessionResponse,
)
from app.schemas.menu import MenuResponse, UpsellsResponse
from app.schemas.offer import PublicOfferResponse
from app.schemas.order import OrderResponse
from app.schemas.restaurant import PublicRestaurantResponse
from app.schemas.waiter_call import CreateWaiterCallRequest, WaiterCallResponse
from app.services.analytics import AnalyticsService
from app.services.customer import CustomerService
from app.services.menu import MenuService
from app.services.offer import OfferService
from app.services.order import OrderService
from app.services.public_state import resolve_serving_state
from app.services.waiter_call import WaiterCallService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/restaurants/{slug}", response_model=PublicRestaurantResponse)
async def get_public_restaurant_profile(
    restaurant: PublicRestaurant,
    db: DBSession,
    response: Response,
) -> PublicRestaurantResponse:
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
    response_body = PublicRestaurantResponse.model_validate(restaurant)
    # A draft or lapsed venue answers with a calm "unavailable" instead of an
    # error page — the QR itself must never look broken (PRD §30).
    is_serving, reason = await resolve_serving_state(db, restaurant)
    response_body.is_serving = is_serving
    response_body.unavailable_reason = reason
    return response_body


@router.get("/restaurants/{slug}/offers", response_model=list[PublicOfferResponse])
async def get_public_offers(
    restaurant: ServingRestaurant, db: DBSession, response: Response
) -> list[PublicOfferResponse]:
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
    return await OfferService(db).list_public(restaurant.id)


@router.get(
    "/restaurants/{slug}/menu-items/{menu_item_id}/upsells",
    response_model=UpsellsResponse,
)
async def get_public_upsells(
    menu_item_id: uuid.UUID,
    restaurant: ServingRestaurant,
    db: DBSession,
) -> UpsellsResponse:
    return await MenuService(db).get_upsells(
        menu_item_id, restaurant_id=restaurant.id, available_only=True
    )


@router.post(
    "/restaurants/{slug}/events",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
)
async def log_public_event(
    payload: LogEventRequest,
    restaurant: ServingRestaurant,
    db: DBSession,
    _: None = Depends(rate_limit("public")),
) -> Message:
    await AnalyticsService(db).log_public(restaurant.id, payload)
    return Message(message="Recorded.")


@router.get("/restaurants/{slug}/menu", response_model=MenuResponse)
async def get_public_menu(
    restaurant: ServingRestaurant, db: DBSession, response: Response
) -> MenuResponse:
    response.headers["Cache-Control"] = "public, max-age=45, stale-while-revalidate=180"
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


@router.post(
    "/restaurants/{slug}/waiter-calls",
    response_model=WaiterCallResponse,
    status_code=status.HTTP_201_CREATED,
)
async def call_waiter(
    payload: CreateWaiterCallRequest,
    restaurant: ServingRestaurant,
    db: DBSession,
    _: None = Depends(rate_limit("public")),
) -> WaiterCallResponse:
    return await WaiterCallService(db).create_public(restaurant.id, payload)
