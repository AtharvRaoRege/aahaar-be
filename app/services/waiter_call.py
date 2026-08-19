from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.enums import WaiterCallStatus
from app.models.waiter_call import WaiterCall
from app.repositories.restaurant import RestaurantRepository
from app.repositories.waiter_call import WaiterCallRepository
from app.schemas.waiter_call import CreateWaiterCallRequest, WaiterCallResponse
from app.services.notification import NotificationService


class WaiterCallService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calls = WaiterCallRepository(session)
        self.restaurants = RestaurantRepository(session)
        self.notifier = NotificationService(session)

    async def create_public(
        self, restaurant_id: uuid.UUID, payload: CreateWaiterCallRequest
    ) -> WaiterCallResponse:
        restaurant = await self.restaurants.get(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Venue not found.")
        if not restaurant.waiter_call_enabled:
            raise ValidationError("This venue is not offering waiter calls right now.")

        table = payload.table_number.strip()
        if not table:
            raise ValidationError("Scan the table QR so we know where to send the waiter.")

        existing = await self.calls.get_pending_for_table(restaurant_id, table)
        if existing:
            return WaiterCallResponse.model_validate(existing)

        call = WaiterCall(
            restaurant_id=restaurant_id,
            customer_session_id=payload.customer_session_id,
            table_number=table,
            status=WaiterCallStatus.PENDING,
        )
        self.calls.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        await self.notifier.waiter_called(call)
        return WaiterCallResponse.model_validate(call)

    async def list_pending(self, restaurant_id: uuid.UUID) -> list[WaiterCallResponse]:
        rows = await self.calls.list_pending(restaurant_id)
        return [WaiterCallResponse.model_validate(row) for row in rows]

    async def acknowledge(self, restaurant_id: uuid.UUID, call_id: uuid.UUID) -> WaiterCallResponse:
        call = await self.calls.get(call_id)
        if call is None or call.restaurant_id != restaurant_id:
            raise NotFoundError("Waiter call not found.")
        if call.status != WaiterCallStatus.PENDING:
            raise ConflictError("That call was already handled.")
        call.status = WaiterCallStatus.ACKED
        call.acknowledged_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(call)
        await self.notifier.waiter_acked(call)
        return WaiterCallResponse.model_validate(call)
