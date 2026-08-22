from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.enums import ApprovalStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import RefreshToken, User
from app.repositories.restaurant import RestaurantRepository, TenantRepository
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UpdateUserRequest,
    UserResponse,
    WaitlistUserResponse,
)
from app.services.platform_settings import PlatformSettingsService
from app.utils.slugs import random_suffix, slugify


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)
        self.tenants = TenantRepository(session)
        self.restaurants = RestaurantRepository(session)
        self.platform = PlatformSettingsService(session)

    async def _signup_approval_status(self) -> ApprovalStatus:
        if await self.platform.is_open_registration():
            return ApprovalStatus.APPROVED
        return ApprovalStatus.WAITLIST

    # ── Registration ─────────────────────────────────────────
    async def register(self, payload: RegisterRequest) -> tuple[User, TokenResponse]:
        existing = await self.users.get_by_email(payload.email)
        if existing is not None:
            raise ConflictError(
                "An account with this email already exists.",
                code="EMAIL_TAKEN",
            )

        tenant = Tenant(
            name=payload.owner_name,
            slug=await self._unique_tenant_slug(payload.owner_name),
        )
        self.session.add(tenant)
        await self.session.flush()

        approval = await self._signup_approval_status()
        user = User(
            tenant_id=tenant.id,
            email=payload.email.lower(),
            full_name=payload.owner_name,
            phone=_normalize_phone(payload.phone),
            hashed_password=hash_password(payload.password),
            role=UserRole.OWNER,
            is_active=True,
            approval_status=approval,
        )
        self.session.add(user)
        await self.session.flush()

        tokens = await self._start_new_session(user)
        await self.session.commit()
        await self.session.refresh(user)
        if approval == ApprovalStatus.WAITLIST:
            await self._notify_waitlist_if_needed(user)
        return user, tokens

    # ── Login / tokens ───────────────────────────────────────
    async def login(self, payload: LoginRequest) -> tuple[User, TokenResponse]:
        user = await self.users.get_by_email(payload.email)
        if (
            user is None
            or not user.hashed_password
            or not verify_password(payload.password, user.hashed_password)
        ):
            raise UnauthorizedError("Incorrect email or password.", code="BAD_CREDENTIALS")
        if not user.is_active:
            raise ForbiddenError("This account is disabled.", code="ACCOUNT_DISABLED")
        tokens = await self._start_new_session(user)
        await self.session.commit()
        return user, tokens

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid refresh token.", code="INVALID_TOKEN") from exc
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid refresh token.", code="INVALID_TOKEN")

        record = await self.tokens.get_by_hash(hash_token(refresh_token))
        if record is None or record.revoked:
            raise UnauthorizedError("Refresh token is no longer valid.", code="INVALID_TOKEN")
        if record.expires_at < datetime.now(UTC):
            raise UnauthorizedError("Refresh token expired.", code="TOKEN_EXPIRED")

        user = await self.users.get(record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("Account is not available.", code="ACCOUNT_UNAVAILABLE")

        record.revoked = True  # rotation
        tokens = await self._issue_tokens(user)
        await self.session.commit()
        return tokens

    async def logout(self, refresh_token: str) -> None:
        record = await self.tokens.get_by_hash(hash_token(refresh_token))
        if record is not None:
            record.revoked = True
            await self.session.commit()

    async def sync_clerk_user(self, clerk_token: str) -> tuple[User, TokenResponse]:
        from app.services.clerk import (
            ClerkNotConfiguredError,
            fetch_clerk_profile,
            verify_clerk_session_token,
        )

        if not settings.clerk_enabled:
            raise ClerkNotConfiguredError()

        clerk_user_id = verify_clerk_session_token(clerk_token)
        profile = await fetch_clerk_profile(clerk_user_id)

        user = await self.users.get_by_clerk_id(profile.clerk_user_id)
        if user is None:
            user = await self.users.get_by_email(profile.email)
            if user is not None:
                user.clerk_user_id = profile.clerk_user_id
                if profile.full_name and user.full_name != profile.full_name:
                    user.full_name = profile.full_name

        if user is None:
            tenant = Tenant(
                name=profile.full_name,
                slug=await self._unique_tenant_slug(profile.full_name),
            )
            self.session.add(tenant)
            await self.session.flush()
            approval = await self._signup_approval_status()
            user = User(
                tenant_id=tenant.id,
                email=profile.email,
                full_name=profile.full_name,
                hashed_password=None,
                clerk_user_id=profile.clerk_user_id,
                role=UserRole.OWNER,
                is_active=True,
                approval_status=approval,
            )
            self.session.add(user)
            await self.session.flush()
            created = True
            waitlisted = approval == ApprovalStatus.WAITLIST
        else:
            created = False
            waitlisted = False

        if not user.is_active:
            raise ForbiddenError("This account is disabled.", code="ACCOUNT_DISABLED")

        tokens = await self._start_new_session(user)
        await self.session.commit()
        await self.session.refresh(user)
        if created and waitlisted:
            await self._notify_waitlist_if_needed(user)
        return user, tokens

    async def _start_new_session(self, user: User) -> TokenResponse:
        """Revoke every other device, then mint a fresh session."""
        await self.tokens.revoke_all_for_user(user.id)
        user.session_id = uuid.uuid4()
        await self.session.flush()
        return await self._issue_tokens(user)

    async def _issue_tokens(self, user: User) -> TokenResponse:
        access = create_access_token(
            str(user.id),
            extra={
                "tenantId": str(user.tenant_id),
                "role": user.role.value,
                "sid": str(user.session_id),
            },
        )
        refresh_raw, refresh_hash, expires_at = create_refresh_token(str(user.id))
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=refresh_hash,
                expires_at=expires_at,
                revoked=False,
                created_at=datetime.now(UTC),
            )
        )
        return TokenResponse(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Staff management (tenant scoped) ─────────────────────
    async def list_staff(self, tenant_id: uuid.UUID) -> list[User]:
        return await self.users.list_by_tenant(tenant_id)

    async def create_staff(self, tenant_id: uuid.UUID, payload: CreateUserRequest) -> User:
        if await self.users.get_by_email(payload.email) is not None:
            raise ConflictError("Email already in use.", code="EMAIL_TAKEN")
        user = User(
            tenant_id=tenant_id,
            email=payload.email.lower(),
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=payload.role,
            is_active=True,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_staff(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: UpdateUserRequest
    ) -> User:
        user = await self.users.get(user_id)
        if user is None or user.tenant_id != tenant_id:
            raise NotFoundError("Staff member not found.")
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.password is not None:
            user.hashed_password = hash_password(payload.password)
        if payload.role is not None:
            user.role = payload.role
        if payload.is_active is not None:
            user.is_active = payload.is_active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def to_user_response(self, user: User) -> UserResponse:
        restaurants = await self.restaurants.list_by_tenant(user.tenant_id)
        payload = UserResponse.model_validate(user)
        return payload.model_copy(update={"has_restaurant": len(restaurants) > 0})

    async def update_profile(self, user: User, payload: UpdateProfileRequest) -> User:
        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.phone is not None:
            user.phone = _normalize_phone(payload.phone)
        await self.session.commit()
        await self.session.refresh(user)
        await self._notify_waitlist_if_needed(user)
        return user

    async def list_waitlist(self) -> list[WaitlistUserResponse]:
        users = await self.users.list_waitlist()
        result: list[WaitlistUserResponse] = []
        for user in users:
            base = await self.to_user_response(user)
            result.append(
                WaitlistUserResponse(
                    **base.model_dump(),
                    created_at=user.created_at,
                )
            )
        return result

    async def approve_user(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        user.approval_status = ApprovalStatus.APPROVED
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def _notify_waitlist_if_needed(self, user: User) -> None:
        if user.is_super_admin or user.approval_status != ApprovalStatus.WAITLIST:
            return
        if user.waitlist_notified_at is not None:
            return
        if not user.phone:
            return
        from app.services.outreach import notify_waitlist_join

        await notify_waitlist_join(user)
        user.waitlist_notified_at = datetime.now(UTC)
        await self.session.commit()

    # ── Slug helpers ─────────────────────────────────────────
    async def _unique_tenant_slug(self, name: str) -> str:
        base = slugify(name)
        slug = base
        while await self.tenants.get_by_slug(slug) is not None:
            slug = f"{base}-{random_suffix()}"
        return slug

    async def _unique_restaurant_slug(self, name: str) -> str:
        base = slugify(name)
        slug = base
        while await self.restaurants.slug_exists(slug):
            slug = f"{base}-{random_suffix()}"
        return slug


def get_auth_service(session: AsyncSession) -> AuthService:
    return AuthService(session)


def _normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw.strip() if ch.isdigit() or ch == "+")
    return digits[:32]
