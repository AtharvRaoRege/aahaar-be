from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.dependencies.db import DBSession
from app.models.enums import ApprovalStatus, UserRole
from app.models.user import User
from app.repositories.user import UserRepository

_bearer = HTTPBearer(auto_error=False)


def _decode_supabase_jwt(token: str) -> dict | None:
    """Try to decode as a Supabase-issued JWT (asymmetric or HMAC with anon key)."""
    if not settings.supabase_anon_key:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.supabase_anon_key,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
        return payload
    except jwt.PyJWTError:
        return None


async def get_current_user(
    db: DBSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication required.")

    token = credentials.credentials

    # Try Supabase JWT first
    supa_payload = _decode_supabase_jwt(token)
    if supa_payload:
        supabase_uid = supa_payload.get("sub")
        if not supabase_uid:
            raise UnauthorizedError("Invalid token subject.", code="INVALID_TOKEN")
        user = await UserRepository(db).get_by_supabase_auth_id(uuid.UUID(supabase_uid))
        if user is None or not user.is_active:
            raise UnauthorizedError("Account is not available.", code="ACCOUNT_UNAVAILABLE")
        return user

    # Fall back to legacy custom JWT
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token.", code="INVALID_TOKEN") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type.", code="INVALID_TOKEN")

    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(str(subject))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token subject.", code="INVALID_TOKEN") from exc

    user = await UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account is not available.", code="ACCOUNT_UNAVAILABLE")

    token_sid = payload.get("sid")
    if not token_sid:
        raise UnauthorizedError("Sign in again to continue.", code="TOKEN_STALE")
    if str(user.session_id) != str(token_sid):
        raise UnauthorizedError(
            "This account is signed in on another device.",
            code="SESSION_REPLACED",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_super_admin(user: CurrentUser) -> User:
    if not user.is_super_admin:
        raise ForbiddenError("Super admin access required.", code="NOT_SUPER_ADMIN")
    return user


def assert_approved(user: User) -> None:
    """Reject a kitchen that a super admin has not approved yet.

    Enforced server-side on every kitchen endpoint, not just in the dashboard
    routing — a waitlisted account must not be able to read or change venue data
    by calling the API directly.
    """
    if user.is_super_admin:
        return
    if user.approval_status != ApprovalStatus.APPROVED:
        raise ForbiddenError(
            "Your kitchen is still on the waitlist.",
            code="WAITLISTED",
        )


async def require_approved(user: CurrentUser) -> User:
    assert_approved(user)
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    async def _checker(user: CurrentUser) -> User:
        if user.is_super_admin:
            return user
        assert_approved(user)
        if user.role not in allowed:
            raise ForbiddenError("Your role does not permit this action.", code="INSUFFICIENT_ROLE")
        return user

    return _checker
