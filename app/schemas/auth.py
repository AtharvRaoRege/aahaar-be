from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from app.models.enums import ApprovalStatus, UserRole
from app.schemas.common import CamelModel


class RegisterRequest(CamelModel):
    """Self-service signup. New kitchens stay on the waitlist until a super admin approves."""

    owner_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=8, max_length=32)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class RefreshRequest(CamelModel):
    refresh_token: str


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(CamelModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    full_name: str
    phone: str | None = None
    role: UserRole
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED
    is_super_admin: bool = False
    is_active: bool
    has_restaurant: bool = False


class UpdateProfileRequest(CamelModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=8, max_length=32)


class WaitlistUserResponse(UserResponse):
    created_at: datetime | None = None


class AuthResult(CamelModel):
    """Returned by register/login — the user plus a fresh token pair."""

    user: UserResponse
    tokens: TokenResponse


class CreateUserRequest(CamelModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole = UserRole.RECEPTION


class UpdateUserRequest(CamelModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
