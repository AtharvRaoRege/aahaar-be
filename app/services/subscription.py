"""Subscription lifecycle: trial → active → grace → suspended.

Rules follow PRD §22. Two deliberate choices worth knowing:

* A lapsed venue is **downgraded, never deleted** — Pro data stays but the Pro
  feature set switches off, so re-upgrading restores everything instantly.
* Upgrades apply immediately; downgrades apply at period end via
  ``scheduled_plan``, so nobody loses a feature mid-cycle.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.plans import (
    BILLING_PERIOD_DAYS,
    GRACE_PERIOD_DAYS,
    spec_for,
)
from app.models.enums import PlanRequestStatus, PlanTier, SubscriptionStatus
from app.models.plan_request import PlanRequest
from app.models.subscription import Subscription
from app.repositories.plan_request import PlanRequestRepository
from app.repositories.subscription import SubscriptionRepository
from app.schemas.subscription import (
    AddPaymentMethodRequest,
    CancelSubscriptionRequest,
    PlanSpecResponse,
    SubscriptionResponse,
)

logger = get_logger("aahaar.subscription")


def plan_catalogue() -> list[PlanSpecResponse]:
    return [
        PlanSpecResponse(
            tier=tier,
            monthly_price=spec_for(tier).monthly_price,
            trial_days=spec_for(tier).trial_days,
            table_limit=spec_for(tier).table_limit,
            features=sorted(feature.value for feature in spec_for(tier).features),
            includes=list(spec_for(tier).includes),
        )
        for tier in (PlanTier.BASIC, PlanTier.PRO)
    ]


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = SubscriptionRepository(session)
        self.plan_requests = PlanRequestRepository(session)

    # ── Read ─────────────────────────────────────────────────
    async def get_or_create(self, restaurant_id: uuid.UUID, *, commit: bool = True) -> Subscription:
        """Resolve the venue's subscription, starting a Basic trial if it has none."""
        subscription = await self.subscriptions.get_for_restaurant(restaurant_id)
        if subscription is None:
            basic = spec_for(PlanTier.BASIC)
            subscription = Subscription(
                restaurant_id=restaurant_id,
                plan=PlanTier.BASIC,
                status=SubscriptionStatus.TRIALING,
                monthly_price=basic.monthly_price,
                trial_ends_at=self._now() + timedelta(days=basic.trial_days),
            )
            self.subscriptions.add(subscription)
            if commit:
                await self.session.commit()
                await self.session.refresh(subscription)
            else:
                await self.session.flush()
        return subscription

    async def get_state(
        self,
        restaurant_id: uuid.UUID,
        *,
        elevate_pro: bool = False,
    ) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id)
        if self._advance(subscription):
            await self.session.commit()
            await self.session.refresh(subscription)
        return await self.to_response(subscription, elevate_pro=elevate_pro)

    # ── Mutations ────────────────────────────────────────────
    async def change_plan(self, restaurant_id: uuid.UUID, plan: PlanTier) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id)
        self._advance(subscription)

        if plan == subscription.plan and subscription.scheduled_plan is None:
            raise ConflictError("This venue is already on that plan.")

        if plan == subscription.plan:
            # Cancels a pending downgrade — nothing else changes.
            subscription.scheduled_plan = None
        elif self._is_upgrade(subscription.plan, plan):
            pending = await self.plan_requests.get_pending(restaurant_id)
            if pending:
                raise ConflictError("Your Pro request is already waiting for approval.")
            self.plan_requests.add(
                PlanRequest(
                    restaurant_id=restaurant_id,
                    requested_plan=plan,
                    status=PlanRequestStatus.PENDING,
                )
            )
        else:
            # Downgrade: keep the current feature set until the period ends.
            subscription.scheduled_plan = plan
            if subscription.status == SubscriptionStatus.SUSPENDED:
                self._apply_plan_now(subscription, plan)

        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def add_payment_method(
        self, restaurant_id: uuid.UUID, payload: AddPaymentMethodRequest
    ) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id)
        self._advance(subscription)
        subscription.payment_method_ref = payload.provider_ref.strip()

        # A saved method resolves a lapsed state immediately — start a fresh period.
        if subscription.status in {SubscriptionStatus.GRACE, SubscriptionStatus.SUSPENDED}:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.grace_ends_at = None
            subscription.current_period_end = self._now() + timedelta(days=BILLING_PERIOD_DAYS)
        elif subscription.status == SubscriptionStatus.CANCELLED:
            raise ConflictError("Reactivate the subscription before adding a payment method.")

        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def cancel(
        self, restaurant_id: uuid.UUID, payload: CancelSubscriptionRequest
    ) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id)
        self._advance(subscription)
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise ConflictError("This subscription is already cancelled.")

        # Effective at period end — no partial-month refund (PRD §22).
        subscription.cancel_at_period_end = True
        subscription.cancel_reason = (payload.reason or "").strip() or None
        if subscription.current_period_end is None and subscription.trial_ends_at is None:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = self._now()

        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def resume(self, restaurant_id: uuid.UUID) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id)
        if not subscription.cancel_at_period_end and (
            subscription.status != SubscriptionStatus.CANCELLED
        ):
            raise ConflictError("This subscription is not scheduled to end.")

        subscription.cancel_at_period_end = False
        subscription.cancel_reason = None
        subscription.cancelled_at = None
        if subscription.status == SubscriptionStatus.CANCELLED:
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_period_end = self._now() + timedelta(days=BILLING_PERIOD_DAYS)

        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def approve_plan_request(
        self, request_id: uuid.UUID, reviewer_id: uuid.UUID
    ) -> SubscriptionResponse:
        request = await self.plan_requests.get(request_id)
        if request is None:
            raise NotFoundError("Plan request not found.")
        if request.status != PlanRequestStatus.PENDING:
            raise ConflictError("This request has already been reviewed.")

        subscription = await self.get_or_create(request.restaurant_id, commit=False)
        self._advance(subscription)
        self._apply_upgrade(subscription, request.requested_plan)
        request.status = PlanRequestStatus.APPROVED
        request.reviewed_at = self._now()
        request.reviewed_by = reviewer_id
        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def reject_plan_request(self, request_id: uuid.UUID, reviewer_id: uuid.UUID) -> None:
        request = await self.plan_requests.get(request_id)
        if request is None:
            raise NotFoundError("Plan request not found.")
        if request.status != PlanRequestStatus.PENDING:
            raise ConflictError("This request has already been reviewed.")
        request.status = PlanRequestStatus.REJECTED
        request.reviewed_at = self._now()
        request.reviewed_by = reviewer_id
        await self.session.commit()

    async def admin_assign_plan(
        self, restaurant_id: uuid.UUID, plan: PlanTier, reviewer_id: uuid.UUID
    ) -> SubscriptionResponse:
        subscription = await self.get_or_create(restaurant_id, commit=False)
        self._advance(subscription)
        pending = await self.plan_requests.get_pending(restaurant_id)
        if pending:
            pending.status = (
                PlanRequestStatus.APPROVED
                if pending.requested_plan == plan
                else PlanRequestStatus.REJECTED
            )
            pending.reviewed_at = self._now()
            pending.reviewed_by = reviewer_id
        if plan == PlanTier.PRO:
            if subscription.plan != PlanTier.PRO or subscription.status not in {
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.GRACE,
            }:
                self._apply_upgrade(subscription, plan)
        else:
            self._apply_plan_now(subscription, PlanTier.BASIC)
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.trial_ends_at = None
            subscription.grace_ends_at = None
            subscription.cancelled_at = None
            subscription.cancel_at_period_end = False
            subscription.current_period_end = None
        await self.session.commit()
        await self.session.refresh(subscription)
        return await self.to_response(subscription)

    async def reconcile_all(self) -> int:
        """Advance every non-terminal subscription. Safe to run on a schedule."""
        subscriptions = await self.subscriptions.list_by_statuses(
            [
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.GRACE,
            ]
        )
        changed = sum(1 for subscription in subscriptions if self._advance(subscription))
        if changed:
            await self.session.commit()
            logger.info("Advanced %s subscription(s)", changed)
        return changed

    # ── Response mapping ─────────────────────────────────────
    async def to_response(
        self,
        subscription: Subscription,
        *,
        elevate_pro: bool = False,
    ) -> SubscriptionResponse:
        from app.core.config import settings

        effective = PlanTier.PRO if elevate_pro else subscription.effective_plan
        spec = spec_for(effective)
        pending = await self.plan_requests.get_pending(subscription.restaurant_id)
        return SubscriptionResponse(
            id=subscription.id,
            restaurant_id=subscription.restaurant_id,
            plan=subscription.plan,
            effective_plan=effective,
            status=subscription.status,
            monthly_price=subscription.monthly_price,
            trial_ends_at=subscription.trial_ends_at,
            current_period_end=subscription.current_period_end,
            grace_ends_at=subscription.grace_ends_at,
            pro_trial_used=subscription.pro_trial_used,
            scheduled_plan=subscription.scheduled_plan,
            cancel_at_period_end=subscription.cancel_at_period_end,
            cancel_reason=subscription.cancel_reason,
            has_payment_method=bool(subscription.payment_method_ref),
            days_left=self._days_left(subscription),
            pending_plan=pending.requested_plan if pending else None,
            pending_request_id=pending.id if pending else None,
            table_limit=spec.table_limit,
            features=sorted(feature.value for feature in spec.features),
            # Infra flag only — Pro entitlement is in ``features`` / ``effective_plan``.
            menu_scan_enabled=settings.gemini_enabled,
        )

    # ── Internals ────────────────────────────────────────────
    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _is_upgrade(self, current: PlanTier, target: PlanTier) -> bool:
        return spec_for(target).monthly_price > spec_for(current).monthly_price

    def _apply_upgrade(self, subscription: Subscription, plan: PlanTier) -> None:
        spec = spec_for(plan)
        subscription.plan = plan
        subscription.monthly_price = spec.monthly_price
        subscription.scheduled_plan = None
        subscription.grace_ends_at = None

        if plan == PlanTier.PRO and not subscription.pro_trial_used:
            # First taste of Pro is a trial, not a charge (PRD §8).
            subscription.pro_trial_used = True
            subscription.status = SubscriptionStatus.TRIALING
            subscription.trial_ends_at = self._now() + timedelta(days=spec.trial_days)
            subscription.current_period_end = None
            return

        subscription.status = SubscriptionStatus.ACTIVE
        subscription.trial_ends_at = None
        subscription.current_period_end = self._now() + timedelta(days=BILLING_PERIOD_DAYS)

    def _apply_plan_now(self, subscription: Subscription, plan: PlanTier) -> None:
        subscription.plan = plan
        subscription.monthly_price = spec_for(plan).monthly_price
        subscription.scheduled_plan = None

    def _advance(self, subscription: Subscription) -> bool:
        """Move a subscription forward through its lifecycle. True if it changed."""
        now = self._now()
        changed = False

        if subscription.status == SubscriptionStatus.TRIALING and self._past(
            subscription.trial_ends_at, now
        ):
            subscription.trial_ends_at = None
            if subscription.cancel_at_period_end:
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.cancelled_at = now
            elif subscription.payment_method_ref:
                subscription.status = SubscriptionStatus.ACTIVE
                subscription.current_period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
            else:
                subscription.status = SubscriptionStatus.GRACE
                subscription.grace_ends_at = now + timedelta(days=GRACE_PERIOD_DAYS)
            changed = True

        if subscription.status == SubscriptionStatus.ACTIVE and self._past(
            subscription.current_period_end, now
        ):
            if subscription.scheduled_plan is not None:
                self._apply_plan_now(subscription, subscription.scheduled_plan)
            if subscription.cancel_at_period_end:
                subscription.status = SubscriptionStatus.CANCELLED
                subscription.cancelled_at = now
                subscription.current_period_end = None
            elif subscription.payment_method_ref:
                subscription.current_period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
            else:
                subscription.status = SubscriptionStatus.GRACE
                subscription.grace_ends_at = now + timedelta(days=GRACE_PERIOD_DAYS)
            changed = True

        if subscription.status == SubscriptionStatus.GRACE and self._past(
            subscription.grace_ends_at, now
        ):
            # Data is retained; only the feature set and public menu are gated.
            subscription.status = SubscriptionStatus.SUSPENDED
            subscription.grace_ends_at = None
            changed = True

        return changed

    def _past(self, moment: datetime | None, now: datetime) -> bool:
        if moment is None:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment <= now

    def _days_left(self, subscription: Subscription) -> int | None:
        deadline = (
            subscription.trial_ends_at
            or subscription.grace_ends_at
            or subscription.current_period_end
        )
        if deadline is None:
            return None
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        remaining = deadline - self._now()
        return max(0, remaining.days + (1 if remaining.seconds else 0))
