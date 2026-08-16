from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_super_admin
from app.dependencies.db import DBSession
from app.models.user import User
from app.schemas.admin import AdminRestaurantResponse, AdminUserResponse
from app.schemas.auth import UserResponse, WaitlistUserResponse
from app.services.admin import AdminService
from app.services.auth import AuthService

router = APIRouter(prefix="/admin", tags=["admin"])


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
