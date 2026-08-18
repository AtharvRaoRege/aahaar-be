from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models.customer_session import CustomerSession
from app.repositories.customer import CustomerSessionRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.customer import CreateCustomerSessionRequest

SESSION_TTL_HOURS = 6


def assert_session_active(session: CustomerSession) -> None:
    expires = session.expires_at
    if expires is None:
        return
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC):
        raise ValidationError(
            "This table session has expired. Scan the QR again.",
            code="SESSION_EXPIRED",
        )


class CustomerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sessions = CustomerSessionRepository(session)
        self.restaurants = RestaurantRepository(session)

    async def create_session(self, payload: CreateCustomerSessionRequest) -> CustomerSession:
        restaurant = None
        if payload.restaurant_id is not None:
            restaurant = await self.restaurants.get(payload.restaurant_id)
        elif payload.slug:
            restaurant = await self.restaurants.get_by_slug(payload.slug)
        else:
            raise ValidationError(
                "Either restaurantId or slug is required.", code="RESTAURANT_REQUIRED"
            )

        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found.")

        table = payload.table_number.strip()
        if not table:
            raise ValidationError("A table number is required.", code="TABLE_REQUIRED")

        name = (payload.name or "").strip()
        if not name:
            raise ValidationError("A guest name is required.", code="NAME_REQUIRED")
        contact = (payload.contact_number or "").strip() or None

        customer_session = CustomerSession(
            restaurant_id=restaurant.id,
            name=name,
            contact_number=contact[:32] if contact else None,
            guest_count=payload.guest_count,
            table_number=table,
            room_number=payload.room_number,
            expires_at=datetime.now(UTC) + timedelta(hours=SESSION_TTL_HOURS),
        )
        self.session.add(customer_session)
        await self.session.commit()
        await self.session.refresh(customer_session)
        return customer_session

    async def get_session(self, session_id: uuid.UUID) -> CustomerSession:
        customer_session = await self.sessions.get(session_id)
        if customer_session is None:
            raise NotFoundError("Session not found.")
        assert_session_active(customer_session)
        return customer_session


def get_customer_service(session: AsyncSession) -> CustomerService:
    return CustomerService(session)
