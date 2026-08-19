from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models.customer_session import CustomerSession
from app.models.enums import ACTIVE_STATUSES, OrderStatus
from app.models.order import Order, OrderItem
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    _relations = (
        selectinload(Order.items),
        selectinload(Order.status_history),
        selectinload(Order.customer_session),
        selectinload(Order.review),
    )

    async def get_with_relations(self, order_id: uuid.UUID) -> Order | None:
        result = await self.session.execute(
            select(Order).where(Order.id == order_id).options(*self._relations)
        )
        return result.scalar_one_or_none()

    async def next_order_number(self, restaurant_id: uuid.UUID) -> int:
        """Highest order number for a restaurant + 1.

        The caller must already hold a lock on the restaurant row (see
        ``lock_restaurant``) so concurrent orders cannot collide.
        """
        result = await self.session.execute(
            select(func.coalesce(func.max(Order.order_number), 0)).where(
                Order.restaurant_id == restaurant_id
            )
        )
        return int(result.scalar_one()) + 1

    async def get_open_for_place(
        self,
        restaurant_id: uuid.UUID,
        *,
        table_number: str | None,
        room_number: str | None,
        session_id: uuid.UUID,
    ) -> Order | None:
        """Latest ticket that is still open for this table, room, or session."""
        conditions = [
            Order.restaurant_id == restaurant_id,
            Order.status.in_(list(ACTIVE_STATUSES)),
        ]
        if table_number:
            conditions.append(Order.table_number == table_number)
        elif room_number:
            conditions.append(Order.room_number == room_number)
        else:
            conditions.append(Order.customer_session_id == session_id)

        result = await self.session.execute(
            select(Order)
            .where(*conditions)
            .options(*self._relations)
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_stale_active(self, restaurant_id: uuid.UUID, cutoff: datetime) -> list[Order]:
        """Active tickets untouched since ``cutoff`` — nobody is coming back for these.

        ``updated_at`` keeps a long table that is still adding items out of the sweep.
        """
        result = await self.session.execute(
            select(Order)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.status.in_(list(ACTIVE_STATUSES)),
                Order.created_at < cutoff,
                Order.updated_at < cutoff,
            )
            .options(*self._relations)
            .order_by(Order.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_idempotency_key(self, restaurant_id: uuid.UUID, key: str) -> Order | None:
        result = await self.session.execute(
            select(Order)
            .where(
                Order.restaurant_id == restaurant_id,
                Order.idempotency_key == key,
            )
            .options(*self._relations)
        )
        return result.scalar_one_or_none()

    def _filters(
        self,
        restaurant_id: uuid.UUID,
        *,
        table_number: str | None,
        search: str | None,
        since: datetime | None,
    ) -> list:
        conditions = [Order.restaurant_id == restaurant_id]
        if table_number:
            conditions.append(Order.table_number == table_number)
        if since is not None:
            conditions.append(Order.created_at >= since)
        if search:
            term = f"%{search.strip()}%"
            clauses = [
                Order.table_number.ilike(term),
                Order.room_number.ilike(term),
                Order.items.any(OrderItem.name_snapshot.ilike(term)),
                Order.customer_session.has(CustomerSession.name.ilike(term)),
                Order.customer_session.has(CustomerSession.contact_number.ilike(term)),
            ]
            digits = "".join(ch for ch in search if ch.isdigit())
            if digits:
                clauses.append(Order.order_number == int(digits))
            conditions.append(or_(*clauses))
        return conditions

    async def list_by_restaurant(
        self,
        restaurant_id: uuid.UUID,
        *,
        statuses: Sequence[OrderStatus] | None = None,
        table_number: str | None = None,
        search: str | None = None,
        since: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        conditions = self._filters(
            restaurant_id, table_number=table_number, search=search, since=since
        )
        if statuses:
            conditions.append(Order.status.in_(list(statuses)))

        count_result = await self.session.execute(
            select(func.count()).select_from(Order).where(*conditions)
        )
        total = int(count_result.scalar_one())

        result = await self.session.execute(
            select(Order)
            .where(*conditions)
            .options(*self._relations)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def count_by_status(
        self,
        restaurant_id: uuid.UUID,
        *,
        table_number: str | None = None,
        search: str | None = None,
        since: datetime | None = None,
    ) -> dict[OrderStatus, int]:
        """Totals per status for the given filters, unbounded by page size."""
        conditions = self._filters(
            restaurant_id, table_number=table_number, search=search, since=since
        )
        result = await self.session.execute(
            select(Order.status, func.count()).where(*conditions).group_by(Order.status)
        )
        return {row[0]: int(row[1]) for row in result.all()}
