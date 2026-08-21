from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies.auth import CurrentUser, require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.subscription import (
    AddPaymentMethodRequest,
    CancelSubscriptionRequest,
    ChangePlanRequest,
    PlanSpecResponse,
    SubscriptionResponse,
)
from app.services.subscription import SubscriptionService, plan_catalogue

router = APIRouter(tags=["subscription"])

# Billing is the owner's call — managers and floor staff never see it (PRD §10).
_owner = require_roles(UserRole.OWNER)


@router.get("/plans", response_model=list[PlanSpecResponse])
async def list_plans() -> list[PlanSpecResponse]:
    return plan_catalogue()


@router.get("/restaurants/{restaurant_id}/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    restaurant: OwnedRestaurant,
    db: DBSession,
    user: CurrentUser,
) -> SubscriptionResponse:
    return await SubscriptionService(db).get_state(
        restaurant.id,
        elevate_pro=user.is_super_admin,
    )


@router.post("/restaurants/{restaurant_id}/subscription/plan", response_model=SubscriptionResponse)
async def change_plan(
    payload: ChangePlanRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_owner),
) -> SubscriptionResponse:
    return await SubscriptionService(db).change_plan(restaurant.id, payload.plan)


@router.post(
    "/restaurants/{restaurant_id}/subscription/payment-method",
    response_model=SubscriptionResponse,
)
async def add_payment_method(
    payload: AddPaymentMethodRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_owner),
) -> SubscriptionResponse:
    return await SubscriptionService(db).add_payment_method(restaurant.id, payload)


@router.post(
    "/restaurants/{restaurant_id}/subscription/cancel",
    response_model=SubscriptionResponse,
)
async def cancel_subscription(
    payload: CancelSubscriptionRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_owner),
) -> SubscriptionResponse:
    return await SubscriptionService(db).cancel(restaurant.id, payload)


@router.post(
    "/restaurants/{restaurant_id}/subscription/resume",
    response_model=SubscriptionResponse,
)
async def resume_subscription(
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_owner),
) -> SubscriptionResponse:
    return await SubscriptionService(db).resume(restaurant.id)
