from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, status

from app.core.errors import UnauthorizedError
from app.dependencies.auth import CurrentUser, require_roles
from app.dependencies.db import DBSession
from app.dependencies.rate_limit import rate_limit
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    AuthResult,
    CreateUserRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserRequest,
    UserResponse,
)
from app.schemas.common import Message
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


async def _auth_result(db, user, tokens) -> AuthResult:
    return AuthResult(user=await AuthService(db).to_user_response(user), tokens=tokens)


@router.post("/register", response_model=AuthResult, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: DBSession,
    _: None = Depends(rate_limit("login")),
) -> AuthResult:
    user, tokens = await AuthService(db).register(payload)
    return await _auth_result(db, user, tokens)


@router.post("/login", response_model=AuthResult)
async def login(
    payload: LoginRequest,
    db: DBSession,
    _: None = Depends(rate_limit("login")),
) -> AuthResult:
    user, tokens = await AuthService(db).login(payload)
    return await _auth_result(db, user, tokens)


@router.post("/clerk/sync", response_model=AuthResult)
async def sync_clerk_session(
    db: DBSession,
    authorization: str | None = Header(default=None),
    _: None = Depends(rate_limit("login")),
) -> AuthResult:
    """Exchange a Clerk Google session JWT for Aahaar tokens and upsert the user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Clerk session token required.")
    token = authorization.split(" ", 1)[1].strip()
    user, tokens = await AuthService(db).sync_clerk_user(token)
    return await _auth_result(db, user, tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DBSession) -> TokenResponse:
    return await AuthService(db).refresh(payload.refresh_token)


@router.post("/logout", response_model=Message)
async def logout(payload: RefreshRequest, db: DBSession) -> Message:
    await AuthService(db).logout(payload.refresh_token)
    return Message(message="Logged out.")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser, db: DBSession) -> UserResponse:
    return await AuthService(db).to_user_response(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    user: CurrentUser,
    db: DBSession,
) -> UserResponse:
    service = AuthService(db)
    updated = await service.update_profile(user, payload)
    return await service.to_user_response(updated)


# ── Staff management (OWNER/MANAGER) ─────────────────────────
@router.get("/staff", response_model=list[UserResponse])
async def list_staff(
    db: DBSession,
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> list[UserResponse]:
    service = AuthService(db)
    staff = await service.list_staff(user.tenant_id)
    return [await service.to_user_response(member) for member in staff]


@router.post("/staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: CreateUserRequest,
    db: DBSession,
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> UserResponse:
    service = AuthService(db)
    created = await service.create_staff(user.tenant_id, payload)
    return await service.to_user_response(created)


@router.patch("/staff/{user_id}", response_model=UserResponse)
async def update_staff(
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    db: DBSession,
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> UserResponse:
    service = AuthService(db)
    updated = await service.update_staff(user.tenant_id, user_id, payload)
    return await service.to_user_response(updated)
