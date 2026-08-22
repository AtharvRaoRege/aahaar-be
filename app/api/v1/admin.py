from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import require_super_admin
from app.dependencies.db import DBSession
from app.models.user import User
from app.schemas.admin import (
    AdminAnalyticsResponse,
    AdminRestaurantResponse,
    AdminUserResponse,
    AssignPlanRequest,
    PlanRequestResponse,
    PlatformSettingsResponse,
    SetActiveRequest,
    SetPublishedRequest,
    UpdatePlatformSettingsRequest,
)
from app.schemas.auth import UserResponse, WaitlistUserResponse
from app.schemas.subscription import SubscriptionResponse
from app.services.admin import AdminService
from app.services.auth import AuthService
from app.services.platform_settings import PlatformSettingsService
from app.services.subscription import SubscriptionService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> PlatformSettingsResponse:
    open_registration = await PlatformSettingsService(db).is_open_registration()
    return PlatformSettingsResponse(open_registration=open_registration)


@router.patch("/settings", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    payload: UpdatePlatformSettingsRequest,
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> PlatformSettingsResponse:
    open_registration = await PlatformSettingsService(db).set_open_registration(
        payload.open_registration
    )
    return PlatformSettingsResponse(open_registration=open_registration)


@router.get("/waitlist", response_model=list[WaitlistUserResponse])
async def list_waitlist(
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> list[WaitlistUserResponse]:
    return await AuthService(db).list_waitlist()


@router.post("/waitlist/{user_id}/approve", response_model=UserResponse)
async def approve_waitlist_user(
    user_id: uuid.UUID,
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> UserResponse:
    service = AuthService(db)
    user = await service.approve_user(user_id)
    return await service.to_user_response(user)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> list[AdminUserResponse]:
    return await AdminService(db).list_users()


@router.get("/restaurants", response_model=list[AdminRestaurantResponse])
async def list_restaurants(
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> list[AdminRestaurantResponse]:
    return await AdminService(db).list_restaurants()


@router.get("/analytics", response_model=AdminAnalyticsResponse)
async def platform_analytics(
    db: DBSession,
    _: User = Depends(require_super_admin),
    range_days: int = Query(default=30, ge=1, le=90),
) -> AdminAnalyticsResponse:
    return await AdminService(db).platform_analytics(range_days)


@router.get("/plan-requests", response_model=list[PlanRequestResponse])
async def list_plan_requests(
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> list[PlanRequestResponse]:
    return await AdminService(db).list_plan_requests()


@router.post("/plan-requests/{request_id}/approve", response_model=SubscriptionResponse)
async def approve_plan_request(
    request_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(require_super_admin),
) -> SubscriptionResponse:
    return await SubscriptionService(db).approve_plan_request(request_id, user.id)


@router.post("/plan-requests/{request_id}/reject")
async def reject_plan_request(
    request_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(require_super_admin),
) -> dict[str, bool]:
    await SubscriptionService(db).reject_plan_request(request_id, user.id)
    return {"ok": True}


@router.post("/waitlist/{user_id}/reject")
async def reject_waitlist_user(
    user_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(require_super_admin),
) -> dict[str, bool]:
    await AdminService(db).reject_waitlist(user_id, user)
    return {"ok": True}


@router.post("/users/{user_id}/active", response_model=AdminUserResponse)
async def set_user_active(
    user_id: uuid.UUID,
    payload: SetActiveRequest,
    db: DBSession,
    user: User = Depends(require_super_admin),
) -> AdminUserResponse:
    return await AdminService(db).set_user_active(user_id, payload.is_active, user)


@router.post("/restaurants/{restaurant_id}/publish", response_model=AdminRestaurantResponse)
async def set_restaurant_published(
    restaurant_id: uuid.UUID,
    payload: SetPublishedRequest,
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> AdminRestaurantResponse:
    return await AdminService(db).set_published(restaurant_id, payload.is_published)


@router.post("/restaurants/{restaurant_id}/active", response_model=AdminRestaurantResponse)
async def set_restaurant_active(
    restaurant_id: uuid.UUID,
    payload: SetActiveRequest,
    db: DBSession,
    _: User = Depends(require_super_admin),
) -> AdminRestaurantResponse:
    return await AdminService(db).set_venue_active(restaurant_id, payload.is_active)


@router.post("/restaurants/{restaurant_id}/plan", response_model=SubscriptionResponse)
async def assign_restaurant_plan(
    restaurant_id: uuid.UUID,
    payload: AssignPlanRequest,
    db: DBSession,
    user: User = Depends(require_super_admin),
) -> SubscriptionResponse:
    return await SubscriptionService(db).admin_assign_plan(restaurant_id, payload.plan, user.id)
