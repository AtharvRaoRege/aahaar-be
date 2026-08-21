from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.core.errors import AppError, ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import (
    ACTIVE_STATUSES,
    STATUS_TRANSITIONS,
    TERMINAL_STATUSES,
    AnalyticsEventType,
    OrderStatus,
    path_between,
)
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.restaurant import Restaurant
from app.repositories.customer import CustomerSessionRepository
from app.repositories.menu import MenuItemRepository
from app.repositories.offer import OfferRepository
from app.repositories.order import OrderRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.common import Page, PageParams
from app.schemas.order import (
    CreateOrderRequest,
    OrderCustomerInfo,
    OrderItemRequest,
    OrderItemResponse,
    OrderResponse,
    OrderStageCounts,
    OrderStatusHistoryResponse,
)
from app.services.customer import assert_session_active
from app.services.notification import NotificationService
from app.services.offer_discount import compute_discount

logger = get_logger("aahaar.orders")

_TWO_PLACES = Decimal("0.01")

# Tickets left open this long are stale: the table has long since left.
STALE_ORDER_HOURS = 2


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _service_date(timezone_name: str | None) -> date:
    """Venue-local calendar day used to reset kitchen ticket numbers at midnight."""
    name = (timezone_name or "Asia/Kolkata").strip() or "Asia/Kolkata"
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    return datetime.now(zone).date()


def _join_notes(current: str | None, extra: str | None) -> str | None:
    incoming = (extra or "").strip()
    existing = (current or "").strip()
    if not incoming:
        return current
    if not existing:
        return incoming[:500]
    if incoming in existing:
        return existing
    return f"{existing}\n{incoming}"[:500]


def _line_key(item: OrderItem) -> tuple[str, str, tuple[str, ...], str]:
    variant = ""
    if isinstance(item.variant_snapshot, dict):
        variant = str(item.variant_snapshot.get("id") or "")
    addons: list[str] = []
    if isinstance(item.addon_snapshot, list):
        for addon in item.addon_snapshot:
            if isinstance(addon, dict):
                addons.append(str(addon.get("id") or ""))
    menu_id = str(item.menu_item_id) if item.menu_item_id else item.name_snapshot
    return (menu_id, variant, tuple(sorted(addons)), (item.notes or "").strip())


async def run_order_side_effects(order_id: uuid.UUID, kind: str) -> None:
    """Analytics + push/socket after the guest already got 201.

    Uses a fresh session so the request path never waits on Web Push.
    """
    async with SessionFactory() as session:
        try:
            service = OrderService(session)
            order = await service.orders.get_with_relations(order_id)
            if order is None:
                return
            if kind == "created":
                await service._safe_track_order(order)
                await service._safe_notify("created", order)
            elif kind == "items":
                await service._safe_track_upsells(order)
                await service._safe_notify("items", order)
        except Exception:
            logger.exception("Deferred order side effects failed for %s (%s)", order_id, kind)


class OrderService:
    def __init__(self, session: AsyncSession, notifier: NotificationService | None = None) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.items = MenuItemRepository(session)
        self.sessions = CustomerSessionRepository(session)
        self.restaurants = RestaurantRepository(session)
        self.offers = OfferRepository(session)
        self.notifier = notifier or NotificationService(session)

    # ── Creation (public, transactional) ─────────────────────
    async def create_order(
        self,
        payload: CreateOrderRequest,
        idempotency_key: str | None = None,
        *,
        background: BackgroundTasks | None = None,
    ) -> OrderResponse:
        restaurant = await self.restaurants.get(payload.restaurant_id)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found.")

        # A draft or lapsed venue must not take orders, even by direct API call.
        from app.services.public_state import resolve_serving_state

        is_serving, reason = await resolve_serving_state(self.session, restaurant)
        if not is_serving:
            raise ValidationError(
                "This venue is not accepting orders right now.",
                code="MENU_UNAVAILABLE",
                details={"reason": reason},
            )

        if idempotency_key:
            existing, customer_session, menu_index = await asyncio.gather(
                self.orders.get_by_idempotency_key(restaurant.id, idempotency_key),
                self.sessions.get(payload.customer_session_id),
                self._load_menu_index(payload, restaurant.id),
            )
            if existing is not None:
                return self._serialize(existing)
        else:
            customer_session, menu_index = await asyncio.gather(
                self.sessions.get(payload.customer_session_id),
                self._load_menu_index(payload, restaurant.id),
            )

        if customer_session is None or customer_session.restaurant_id != restaurant.id:
            raise ValidationError(
                "Customer session does not belong to this restaurant.",
                code="INVALID_SESSION",
            )
        assert_session_active(customer_session)

        order_items, subtotal = self._build_items(payload.items, menu_index)

        discount = await self._resolve_discount(
            restaurant.id,
            payload.coupon_code,
            order_items,
            subtotal,
        )
        tax = _money(0)
        total = _money(subtotal - discount + tax)

        # Lock the restaurant row so concurrent orders get distinct numbers
        # and so a second ticket for the same open table cannot race a new card.
        await self.session.execute(
            select(Restaurant.id).where(Restaurant.id == restaurant.id).with_for_update()
        )
        open_order = await self.orders.get_open_for_place(
            restaurant.id,
            table_number=customer_session.table_number,
            room_number=customer_session.room_number,
            session_id=customer_session.id,
        )
        if open_order is not None:
            return await self._append_to_order(
                open_order,
                order_items,
                notes=payload.notes,
                idempotency_key=idempotency_key,
                background=background,
            )

        service_day = _service_date(restaurant.timezone)
        order_number = await self.orders.next_order_number(restaurant.id, service_day)
        order = Order(
            restaurant_id=restaurant.id,
            customer_session_id=customer_session.id,
            order_number=order_number,
            service_date=service_day,
            status=OrderStatus.PENDING,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            total=total,
            table_number=customer_session.table_number,
            room_number=customer_session.room_number,
            notes=payload.notes,
            idempotency_key=idempotency_key,
        )
        order.items = order_items
        order.status_history = [OrderStatusHistory(old_status=None, new_status=OrderStatus.PENDING)]
        order.customer_session = customer_session
        self.session.add(order)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if idempotency_key:
                existing = await self.orders.get_by_idempotency_key(restaurant.id, idempotency_key)
                if existing is not None:
                    return self._serialize(existing)
            raise ValidationError(
                "Could not place this order. Try again.",
                code="ORDER_CONFLICT",
            ) from exc

        # Reload after commit so server-default timestamps are present — skipping
        # this returned incomplete JSON and the guest saw a network error.
        created = await self.orders.get_with_relations(order.id)
        assert created is not None
        response = self._serialize(created)
        await self._schedule_side_effects(background, created.id, "created")
        return response

    async def _load_menu_index(
        self, payload: CreateOrderRequest, restaurant_id: uuid.UUID
    ) -> dict[uuid.UUID, MenuItem]:
        return await self._menu_index_for_lines(payload.items, restaurant_id)

    async def _menu_index_for_lines(
        self, lines: list[OrderItemRequest], restaurant_id: uuid.UUID
    ) -> dict[uuid.UUID, MenuItem]:
        item_ids = [line.menu_item_id for line in lines]
        items = await self.items.list_by_ids(item_ids, restaurant_id)
        return {item.id: item for item in items}

    def _build_items(
        self,
        lines: list[OrderItemRequest],
        menu_index: dict[uuid.UUID, MenuItem],
    ) -> tuple[list[OrderItem], Decimal]:
        order_items: list[OrderItem] = []
        subtotal = Decimal("0")

        for line in lines:
            item = menu_index.get(line.menu_item_id)
            if item is None:
                raise AppError(
                    "A selected item is not on this menu.",
                    code="MENU_ITEM_NOT_FOUND",
                    status_code=404,
                )
            if not item.is_available:
                raise AppError(
                    f"'{item.name}' is currently unavailable.",
                    code="MENU_ITEM_UNAVAILABLE",
                    status_code=409,
                )

            if item.variants and line.variant_id is None:
                raise ValidationError(
                    f"Please choose a size for '{item.name}'.",
                    code="VARIANT_REQUIRED",
                )

            unit_price = Decimal(item.base_price)
            variant_snapshot: dict[str, Any] | None = None
            if line.variant_id is not None:
                variant = next((v for v in item.variants if v.id == line.variant_id), None)
                if variant is None:
                    raise ValidationError(
                        f"Invalid variant for '{item.name}'.", code="INVALID_VARIANT"
                    )
                unit_price += Decimal(variant.price_delta)
                variant_snapshot = {
                    "id": str(variant.id),
                    "name": variant.name,
                    "priceDelta": float(variant.price_delta),
                }

            addon_snapshot: list[dict[str, Any]] = []
            if line.addon_ids:
                available = {a.id: a for a in item.addons if a.is_available}
                for addon_id in line.addon_ids:
                    addon = available.get(addon_id)
                    if addon is None:
                        raise ValidationError(
                            f"Invalid or unavailable add-on for '{item.name}'.",
                            code="INVALID_ADDON",
                        )
                    unit_price += Decimal(addon.price)
                    addon_snapshot.append(
                        {
                            "id": str(addon.id),
                            "name": addon.name,
                            "price": float(addon.price),
                        }
                    )

            unit_price = _money(unit_price)
            line_subtotal = _money(unit_price * line.quantity)
            subtotal += line_subtotal

            order_items.append(
                OrderItem(
                    menu_item_id=item.id,
                    name_snapshot=item.name,
                    price_snapshot=unit_price,
                    quantity=line.quantity,
                    variant_snapshot=variant_snapshot,
                    addon_snapshot=addon_snapshot or None,
                    notes=line.notes,
                    subtotal=line_subtotal,
                )
            )

        return order_items, _money(subtotal)

    async def _resolve_discount(
        self,
        restaurant_id: uuid.UUID,
        coupon_code: str | None,
        order_items: list[OrderItem],
        subtotal: Decimal,
    ) -> Decimal:
        if not (coupon_code or "").strip():
            return _money(0)
        _offer, discount = await self._apply_coupon(
            restaurant_id, coupon_code, order_items, subtotal
        )
        return discount

    async def _apply_coupon(
        self,
        restaurant_id: uuid.UUID,
        coupon_code: str | None,
        order_items: list[OrderItem],
        subtotal: Decimal,
    ):
        code = (coupon_code or "").strip()
        if not code:
            raise ValidationError("Enter an offer code.", code="OFFER_INVALID")
        offer = await self.offers.find_live_by_coupon(
            restaurant_id, code, datetime.now(UTC)
        )
        if offer is None:
            raise ValidationError(
                "That code is not valid right now.",
                code="OFFER_INVALID",
            )
        units: list[Decimal] = []
        for item in order_items:
            for _ in range(item.quantity):
                units.append(_money(item.price_snapshot))
        discount = compute_discount(offer, subtotal=_money(subtotal), units=units)
        return offer, discount

    async def verify_coupon(
        self,
        restaurant_id: uuid.UUID,
        coupon_code: str,
        items: list[OrderItemRequest],
    ):
        from app.schemas.offer import VerifyOfferResponse

        menu_index = await self._menu_index_for_lines(items, restaurant_id)
        order_items, subtotal = self._build_items(items, menu_index)
        offer, discount = await self._apply_coupon(
            restaurant_id, coupon_code, order_items, subtotal
        )
        total = _money(subtotal - discount)
        code = (offer.coupon_code or coupon_code).strip().upper()
        return VerifyOfferResponse(
            offer_id=offer.id,
            title=offer.title,
            coupon_code=code,
            discount=discount,
            subtotal=subtotal,
            total=total,
        )

    async def _append_to_order(
        self,
        order: Order,
        incoming: list[OrderItem],
        *,
        notes: str | None,
        idempotency_key: str | None,
        background: BackgroundTasks | None = None,
    ) -> OrderResponse:
        self._merge_items(order, incoming)
        order.subtotal = _money(sum((item.subtotal for item in order.items), Decimal("0")))
        order.total = _money(order.subtotal - order.discount + order.tax)
        order.notes = _join_notes(order.notes, notes)
        if idempotency_key:
            order.idempotency_key = idempotency_key

        if order.status in {OrderStatus.READY, OrderStatus.SERVED}:
            old_status = order.status
            order.status = OrderStatus.PREPARING
            order.status_history.append(
                OrderStatusHistory(
                    old_status=old_status,
                    new_status=OrderStatus.PREPARING,
                    note="Guest added items",
                )
            )

        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if idempotency_key:
                existing = await self.orders.get_by_idempotency_key(
                    order.restaurant_id, idempotency_key
                )
                if existing is not None:
                    return self._serialize(existing)
            raise ValidationError(
                "Could not update this order. Try again.",
                code="ORDER_CONFLICT",
            ) from exc

        updated = await self.orders.get_with_relations(order.id)
        assert updated is not None
        response = self._serialize(updated)
        await self._schedule_side_effects(background, updated.id, "items")
        return response

    async def _schedule_side_effects(
        self,
        background: BackgroundTasks | None,
        order_id: uuid.UUID,
        kind: str,
    ) -> None:
        if background is not None:
            background.add_task(run_order_side_effects, order_id, kind)
            return
        await run_order_side_effects(order_id, kind)

    def _merge_items(self, order: Order, incoming: list[OrderItem]) -> None:
        existing_by_key = {_line_key(item): item for item in order.items}
        for line in incoming:
            match = existing_by_key.get(_line_key(line))
            if match is None:
                order.items.append(line)
                existing_by_key[_line_key(line)] = line
                continue
            match.quantity += line.quantity
            match.subtotal = _money(match.price_snapshot * match.quantity)

    # ── Stale sweep ──────────────────────────────────────────
    async def auto_close_stale(self, restaurant_id: uuid.UUID) -> int:
        """Close tickets nobody finished, so tables and dashboards start clean.

        Runs on dashboard/session reads — not on the guest place-order hot path.
        Bypasses ``STATUS_TRANSITIONS`` because this is a system sweep.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=STALE_ORDER_HOURS)
        stale = await self.orders.list_stale_active(restaurant_id, cutoff)
        if not stale:
            return 0

        for order in stale:
            old_status = order.status
            order.status = OrderStatus.COMPLETED
            order.status_history.append(
                OrderStatusHistory(
                    old_status=old_status,
                    new_status=OrderStatus.COMPLETED,
                    note=f"Auto-closed after {STALE_ORDER_HOURS}h without completion",
                )
            )
        await self.session.commit()

        for order in stale:
            refreshed = await self.orders.get_with_relations(order.id)
            if refreshed is not None:
                await self._safe_notify("status", refreshed)
        return len(stale)

    async def get_open_for_session(self, session_id: uuid.UUID) -> OrderResponse | None:
        customer_session = await self.sessions.get(session_id)
        if customer_session is None:
            raise NotFoundError("Session not found.")
        assert_session_active(customer_session)
        await self.auto_close_stale(customer_session.restaurant_id)
        order = await self.orders.get_open_for_place(
            customer_session.restaurant_id,
            table_number=customer_session.table_number,
            room_number=customer_session.room_number,
            session_id=customer_session.id,
        )
        if order is None:
            return None
        return self._serialize(order)

    # ── Reads ────────────────────────────────────────────────
    async def get_public_order(self, order_id: uuid.UUID) -> OrderResponse:
        order = await self.orders.get_with_relations(order_id)
        if order is None:
            raise NotFoundError("Order not found.")
        return self._serialize(order)

    async def get_owned_order(self, order_id: uuid.UUID, tenant_id: uuid.UUID) -> OrderResponse:
        order = await self._load_owned(order_id, tenant_id)
        return self._serialize(order)

    async def stage_counts(
        self,
        restaurant_id: uuid.UUID,
        *,
        table_number: str | None = None,
        search: str | None = None,
        since_hours: int | None = None,
    ) -> OrderStageCounts:
        """Counts for the orders tabs, using the same filters as the list.

        Computed in the database rather than by counting a fetched page, so the
        tabs still tell the truth on a day with hundreds of tickets.
        """
        await self.auto_close_stale(restaurant_id)
        since = datetime.now(UTC) - timedelta(hours=since_hours) if since_hours else None
        totals = await self.orders.count_by_status(
            restaurant_id,
            table_number=(table_number or None),
            search=(search or None),
            since=since,
        )
        counts = OrderStageCounts()
        for status, count in totals.items():
            if status == OrderStatus.PENDING:
                counts.new += count
            elif status in {OrderStatus.ACCEPTED, OrderStatus.PREPARING}:
                counts.cooking += count
            elif status in {OrderStatus.READY, OrderStatus.SERVED}:
                counts.ready += count
            else:
                counts.closed += count
            counts.all += count
        return counts

    async def list_orders(
        self,
        restaurant_id: uuid.UUID,
        *,
        statuses: list[OrderStatus] | None,
        active_only: bool,
        params: PageParams,
        table_number: str | None = None,
        search: str | None = None,
        since_hours: int | None = None,
    ) -> Page[OrderResponse]:
        await self.auto_close_stale(restaurant_id)
        effective = statuses
        if active_only and not statuses:
            effective = list(ACTIVE_STATUSES)
        since = datetime.now(UTC) - timedelta(hours=since_hours) if since_hours else None
        orders, total = await self.orders.list_by_restaurant(
            restaurant_id,
            statuses=effective,
            table_number=(table_number or None),
            search=(search or None),
            since=since,
            limit=params.page_size,
            offset=params.offset,
        )
        return Page.create([self._serialize(o) for o in orders], total, params)

    # ── Staff transitions ────────────────────────────────────
    async def accept_order(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        allow_cross_tenant: bool = False,
    ) -> OrderResponse:
        return await self._transition(
            order_id,
            tenant_id,
            user_id,
            OrderStatus.ACCEPTED,
            notify="accepted",
            allow_cross_tenant=allow_cross_tenant,
        )

    async def reject_order(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        note: str | None,
        *,
        allow_cross_tenant: bool = False,
    ) -> OrderResponse:
        return await self._transition(
            order_id,
            tenant_id,
            user_id,
            OrderStatus.REJECTED,
            note=note,
            notify="rejected",
            allow_cross_tenant=allow_cross_tenant,
        )

    async def update_status(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        new_status: OrderStatus,
        note: str | None,
        *,
        allow_cross_tenant: bool = False,
    ) -> OrderResponse:
        return await self._transition(
            order_id,
            tenant_id,
            user_id,
            new_status,
            note=note,
            notify="status",
            allow_cross_tenant=allow_cross_tenant,
        )

    async def advance_to(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        target: OrderStatus,
        *,
        allow_cross_tenant: bool = False,
    ) -> OrderResponse:
        """Move an order forward to ``target`` in one call.

        Staff work three stages, not six, so a single tap may cross more than one
        status. Each intermediate hop is still appended to the status history, so
        the record keeps the full lifecycle while the screen stays quick to work.
        """
        await self.session.execute(select(Order.id).where(Order.id == order_id).with_for_update())
        order = await self._load_owned(order_id, tenant_id, allow_cross_tenant=allow_cross_tenant)

        if order.status in TERMINAL_STATUSES:
            raise ValidationError(
                f"Order is already {order.status.value.lower()} and cannot change.",
                code="ORDER_TERMINAL",
            )

        steps = path_between(order.status, target)
        if not steps:
            raise ValidationError(
                f"Cannot move an order from {order.status.value} to {target.value}.",
                code="INVALID_TRANSITION",
            )

        for step in steps:
            order.status_history.append(
                OrderStatusHistory(
                    old_status=order.status,
                    new_status=step,
                    changed_by=user_id,
                )
            )
            order.status = step
        await self.session.commit()

        refreshed = await self.orders.get_with_relations(order.id)
        assert refreshed is not None
        if target == OrderStatus.COMPLETED:
            await self._safe_track_completion(refreshed)
        await self._safe_notify("status", refreshed)
        return self._serialize(refreshed)

    async def _transition(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        new_status: OrderStatus,
        *,
        note: str | None = None,
        notify: str,
        allow_cross_tenant: bool = False,
    ) -> OrderResponse:
        await self.session.execute(select(Order.id).where(Order.id == order_id).with_for_update())
        order = await self._load_owned(order_id, tenant_id, allow_cross_tenant=allow_cross_tenant)
        old_status = order.status

        if old_status in TERMINAL_STATUSES:
            raise ValidationError(
                f"Order is already {old_status.value.lower()} and cannot change.",
                code="ORDER_TERMINAL",
            )
        if new_status not in STATUS_TRANSITIONS.get(old_status, set()):
            raise ValidationError(
                f"Cannot move an order from {old_status.value} to {new_status.value}.",
                code="INVALID_TRANSITION",
            )

        order.status = new_status
        order.status_history.append(
            OrderStatusHistory(
                old_status=old_status,
                new_status=new_status,
                changed_by=user_id,
                note=note,
            )
        )
        await self.session.commit()

        refreshed = await self.orders.get_with_relations(order.id)
        assert refreshed is not None
        if new_status == OrderStatus.COMPLETED:
            await self._safe_track_completion(refreshed)
        await self._safe_notify(notify, refreshed)
        return self._serialize(refreshed)

    async def _safe_track_completion(self, order: Order) -> None:
        from app.services.analytics import AnalyticsService

        try:
            await AnalyticsService(self.session).log(
                order.restaurant_id,
                AnalyticsEventType.ORDER_COMPLETED,
                customer_session_id=order.customer_session_id,
                table_number=order.table_number,
                target_id=order.id,
                meta={"total": str(order.total)},
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Analytics completion tracking failed for order %s", order.id)

    async def _safe_track_upsells(self, order: Order) -> None:
        """Attribute any newly accepted suggestions. Best-effort, never fatal."""
        from app.services.analytics import AnalyticsService

        try:
            await AnalyticsService(self.session).log_order_upsells(order.id, order.restaurant_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Upsell attribution failed for order %s", order.id)

    async def _safe_track_order(self, order: Order) -> None:
        """Log the order event and freeze upsell attribution.

        Analytics must never be able to fail an order that already committed, so
        this is best-effort and swallows its own errors.
        """
        from app.services.analytics import AnalyticsService

        try:
            analytics = AnalyticsService(self.session)
            await analytics.log(
                order.restaurant_id,
                AnalyticsEventType.ORDER_PLACED,
                customer_session_id=order.customer_session_id,
                table_number=order.table_number,
                target_id=order.id,
                meta={"total": str(order.total)},
            )
            await analytics.log_order_upsells(order.id, order.restaurant_id)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Analytics tracking failed for order %s", order.id)

    async def _safe_notify(self, kind: str, order: Order) -> None:
        try:
            if kind == "created":
                await self.notifier.order_created(order)
            elif kind == "items":
                await self.notifier.order_items_added(order)
            elif kind == "accepted":
                await self.notifier.order_accepted(order)
            elif kind == "rejected":
                await self.notifier.order_rejected(order)
            else:
                await self.notifier.order_status_changed(order)
        except Exception:
            logger.exception("Socket notify failed for order %s (%s)", order.id, kind)

    async def _load_owned(
        self,
        order_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        allow_cross_tenant: bool = False,
    ) -> Order:
        order = await self.orders.get_with_relations(order_id)
        if order is None:
            raise NotFoundError("Order not found.")
        if allow_cross_tenant:
            restaurant = await self.restaurants.get(order.restaurant_id)
        else:
            restaurant = await self.restaurants.get_for_tenant(order.restaurant_id, tenant_id)
        if restaurant is None:
            raise ForbiddenError("This order belongs to another tenant.")
        return order

    # ── Serialization ────────────────────────────────────────
    def _serialize(self, order: Order) -> OrderResponse:
        customer = None
        if order.customer_session is not None:
            cs = order.customer_session
            customer = OrderCustomerInfo(
                name=cs.name,
                contact_number=cs.contact_number,
                guest_count=cs.guest_count,
            )
        reviewed = False
        state = sa_inspect(order)
        if "review" not in state.unloaded:
            reviewed = order.review is not None
        return OrderResponse(
            id=order.id,
            restaurant_id=order.restaurant_id,
            customer_session_id=order.customer_session_id,
            order_number=order.order_number,
            status=order.status,
            subtotal=order.subtotal,
            discount=order.discount,
            tax=order.tax,
            total=order.total,
            table_number=order.table_number,
            room_number=order.room_number,
            notes=order.notes,
            created_at=order.created_at,
            updated_at=order.updated_at,
            customer=customer,
            reviewed=reviewed,
            items=[OrderItemResponse.model_validate(i) for i in order.items],
            status_history=[
                OrderStatusHistoryResponse.model_validate(h) for h in order.status_history
            ],
        )


def get_order_service(session: AsyncSession) -> OrderService:
    return OrderService(session)
