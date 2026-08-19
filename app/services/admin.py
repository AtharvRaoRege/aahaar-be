from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import ApprovalStatus, UserRole
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription
from app.models.user import User
from app.repositories.plan_request import PlanRequestRepository
from app.repositories.restaurant import RestaurantRepository
from app.repositories.subscription import SubscriptionRepository
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.admin import AdminRestaurantResponse, AdminUserResponse, PlanRequestResponse


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.restaurants = RestaurantRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.plan_requests = PlanRequestRepository(session)

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
        subscriptions = await self.subscriptions.list_for_restaurants(
            [venue.id for venue in venues]
        )
        subscription_by_venue = {item.restaurant_id: item for item in subscriptions}
        return [
            self._venue_row(
                venue,
                owner_by_tenant.get(venue.tenant_id),
                subscription_by_venue.get(venue.id),
            )
            for venue in venues
        ]

    async def list_plan_requests(self) -> list[PlanRequestResponse]:
        requests = await self.plan_requests.list_pending()
        if not requests:
            return []
        venues = await self.restaurants.list_all()
        venue_by_id = {venue.id: venue for venue in venues}
        users = await self.users.list_all()
        owner_by_tenant: dict[uuid.UUID, User] = {}
        for user in users:
            if user.role == UserRole.OWNER and user.tenant_id not in owner_by_tenant:
                owner_by_tenant[user.tenant_id] = user
        for user in users:
            owner_by_tenant.setdefault(user.tenant_id, user)

        rows: list[PlanRequestResponse] = []
        for request in requests:
            venue = venue_by_id.get(request.restaurant_id)
            owner = owner_by_tenant.get(venue.tenant_id) if venue else None
            rows.append(
                PlanRequestResponse(
                    id=request.id,
                    restaurant_id=request.restaurant_id,
                    restaurant_name=venue.name if venue else "",
                    requested_plan=request.requested_plan,
                    status=request.status,
                    owner_name=owner.full_name if owner else None,
                    owner_email=owner.email if owner else None,
                    owner_phone=(
                        owner.phone if owner and owner.phone else (venue.phone if venue else None)
                    ),
                    created_at=request.created_at,
                )
            )
        return rows

    async def reject_waitlist(self, user_id: uuid.UUID, actor: User) -> None:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        if user.id == actor.id:
            raise ForbiddenError("You cannot reject your own account.")
        if user.approval_status != ApprovalStatus.WAITLIST:
            raise ConflictError("This person is not waiting for approval.")
        user.is_active = False
        await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
        await self.session.commit()

    async def set_user_active(
        self, user_id: uuid.UUID, is_active: bool, actor: User
    ) -> AdminUserResponse:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        if user.id == actor.id and not is_active:
            raise ForbiddenError("You cannot lock your own account.")
        user.is_active = is_active
        if not is_active:
            await RefreshTokenRepository(self.session).revoke_all_for_user(user.id)
        await self.session.commit()
        await self.session.refresh(user)
        venues = await self.restaurants.list_all()
        venue = next((row for row in venues if row.tenant_id == user.tenant_id), None)
        return self._user_row(user, venue)

    async def set_published(
        self, restaurant_id: uuid.UUID, is_published: bool
    ) -> AdminRestaurantResponse:
        venue = await self.restaurants.get(restaurant_id)
        if venue is None:
            raise NotFoundError("Venue not found.")
        venue.is_published = is_published
        await self.session.commit()
        await self.session.refresh(venue)
        return await self._venue_response(venue)

    async def set_venue_active(
        self, restaurant_id: uuid.UUID, is_active: bool
    ) -> AdminRestaurantResponse:
        venue = await self.restaurants.get(restaurant_id)
        if venue is None:
            raise NotFoundError("Venue not found.")
        venue.is_active = is_active
        await self.session.commit()
        await self.session.refresh(venue)
        return await self._venue_response(venue)

    async def _venue_response(self, venue: Restaurant) -> AdminRestaurantResponse:
        users = await self.users.list_all()
        owner = next(
            (
                user
                for user in users
                if user.tenant_id == venue.tenant_id and user.role == UserRole.OWNER
            ),
            None,
        )
        if owner is None:
            owner = next((user for user in users if user.tenant_id == venue.tenant_id), None)
        subscriptions = await self.subscriptions.list_for_restaurants([venue.id])
        subscription = subscriptions[0] if subscriptions else None
        return self._venue_row(venue, owner, subscription)

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

    def _venue_row(
        self,
        venue: Restaurant,
        owner: User | None,
        subscription: Subscription | None,
    ) -> AdminRestaurantResponse:
        return AdminRestaurantResponse.model_validate(venue).model_copy(
            update={
                "owner_id": owner.id if owner else None,
                "owner_name": owner.full_name if owner else None,
                "owner_email": owner.email if owner else None,
                "owner_phone": (owner.phone if owner and owner.phone else venue.phone),
                "created_at": venue.created_at,
                "plan": subscription.plan if subscription else None,
                "subscription_status": subscription.status if subscription else None,
                "trial_ends_at": subscription.trial_ends_at if subscription else None,
                "current_period_end": (subscription.current_period_end if subscription else None),
            }
        )
