from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_clerk_id(self, clerk_user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.clerk_user_id == clerk_user_id))
        return result.scalar_one_or_none()

    async def get_by_supabase_auth_id(self, supabase_auth_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.supabase_auth_id == supabase_auth_id)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
        )
        return list(result.scalars().all())

    async def list_waitlist(self) -> list[User]:
        from app.models.enums import ApprovalStatus

        result = await self.session.execute(
            select(User)
            .where(
                User.approval_status == ApprovalStatus.WAITLIST,
                User.is_active.is_(True),
            )
            .order_by(User.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.created_at.desc()))
        return list(result.scalars().all())


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
            )
        )
        for token in result.scalars().all():
            token.revoked = True
