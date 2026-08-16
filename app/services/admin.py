from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.restaurant import Restaurant
from app.models.user import User
from app.repositories.restaurant import RestaurantRepository
from app.repositories.user import UserRepository
from app.schemas.admin import AdminRestaurantResponse, AdminUserResponse


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.restaurants = RestaurantRepository(session)

    async def list_users(self) -> list[AdminUserResponse]:
        users = await self.users.list_all()
        venues = await self.restaurants.list_all()
        venue_by_tenant = {venue.tenant_id: venue for venue in venues}
        return [self._user_row(user, venue_by_tenant.get(user.tenant_id)) for user in users]

    async def list_restaurants(self) -> list[AdminRestaurantResponse]:
        venues = await self.restaurants.list_all()
        users = await self.users.list_all()
        owner_by_tenant: dict[uuid.UUID, User] = {}
        for user in users:
            if user.tenant_id in owner_by_tenant:
                continue
            if user.role == UserRole.OWNER:
                owner_by_tenant[user.tenant_id] = user
        for user in users:
            owner_by_tenant.setdefault(user.tenant_id, user)
        return [self._venue_row(venue, owner_by_tenant.get(venue.tenant_id)) for venue in venues]

    def _user_row(self, user: User, venue: Restaurant | None) -> AdminUserResponse:
        return AdminUserResponse(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            role=user.role,
            approval_status=user.approval_status,
            is_super_admin=user.is_super_admin,
            is_active=user.is_active,
            has_restaurant=venue is not None,
            created_at=user.created_at,
            restaurant_id=venue.id if venue else None,
            restaurant_name=venue.name if venue else None,
            venue_kind=venue.venue_kind if venue else None,
        )

    def _venue_row(self, venue: Restaurant, owner: User | None) -> AdminRestaurantResponse:
        return AdminRestaurantResponse.model_validate(venue).model_copy(
            update={
                "owner_id": owner.id if owner else None,
                "owner_name": owner.full_name if owner else None,
                "owner_email": owner.email if owner else None,
                "created_at": venue.created_at,
            }
        )
