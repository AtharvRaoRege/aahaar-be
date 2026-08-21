"""Offers shown on the customer menu.

Display-only in v1 (PRD §17): the coupon code is shown to the diner and to staff,
but no discount is applied to the order total. Stacking rules and a price engine
are Phase 2 — shipping them early would put arithmetic bugs on live bills.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.plans import BASIC_OFFER_KINDS, PlanFeature, has_feature
from app.models.enums import OfferKind, OfferState, PlanTier
from app.models.offer import Offer
from app.repositories.offer import OfferRepository
from app.schemas.offer import (
    CreateOfferRequest,
    OfferResponse,
    PublicOfferResponse,
    UpdateOfferRequest,
)
from app.services.subscription import SubscriptionService


class OfferService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.offers = OfferRepository(session)

    async def list_for_restaurant(self, restaurant_id: uuid.UUID) -> list[OfferResponse]:
        offers = await self.offers.list_by_restaurant(restaurant_id)
        return [self._to_response(offer) for offer in offers]

    async def list_public(self, restaurant_id: uuid.UUID) -> list[PublicOfferResponse]:
        offers = await self.offers.list_live(restaurant_id, self._now())
        return [
            PublicOfferResponse(
                id=offer.id,
                kind=offer.kind,
                title=offer.title,
                description=offer.description,
                terms=offer.terms,
                image_url=offer.image_url,
                coupon_code=offer.coupon_code,
                value=offer.value,
                ends_at=offer.ends_at,
            )
            for offer in offers
        ]

    async def create(
        self,
        restaurant_id: uuid.UUID,
        payload: CreateOfferRequest,
        *,
        elevate_pro: bool = False,
    ) -> OfferResponse:
        await self._assert_kind_allowed(restaurant_id, payload.kind, elevate_pro=elevate_pro)
        offer = Offer(restaurant_id=restaurant_id, **payload.model_dump())
        self.offers.add(offer)
        await self.session.commit()
        await self.session.refresh(offer)
        return self._to_response(offer)

    async def update(
        self,
        offer_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        payload: UpdateOfferRequest,
        *,
        elevate_pro: bool = False,
    ) -> OfferResponse:
        offer = await self._get_owned(offer_id, restaurant_id)
        data = payload.model_dump(exclude_unset=True)
        if "kind" in data and data["kind"] is not None:
            await self._assert_kind_allowed(restaurant_id, data["kind"], elevate_pro=elevate_pro)
        for field, value in data.items():
            setattr(offer, field, value)
        await self.session.commit()
        await self.session.refresh(offer)
        return self._to_response(offer)

    async def delete(self, offer_id: uuid.UUID, restaurant_id: uuid.UUID) -> None:
        offer = await self._get_owned(offer_id, restaurant_id)
        await self.session.delete(offer)
        await self.session.commit()

    async def _get_owned(self, offer_id: uuid.UUID, restaurant_id: uuid.UUID) -> Offer:
        offer = await self.offers.get_for_restaurant(offer_id, restaurant_id)
        if offer is None:
            raise NotFoundError("Offer not found.")
        return offer

    async def _assert_kind_allowed(
        self,
        restaurant_id: uuid.UUID,
        kind: OfferKind,
        *,
        elevate_pro: bool = False,
    ) -> None:
        if elevate_pro or kind.value in BASIC_OFFER_KINDS:
            return
        subscription = await SubscriptionService(self.session).get_or_create(restaurant_id)
        if not has_feature(subscription.effective_plan, PlanFeature.ALL_OFFER_TYPES):
            raise ForbiddenError(
                "Percentage and flat offers are on Basic. "
                "BOGO, combo, happy hour and special-day offers need Pro.",
                code="PLAN_UPGRADE_REQUIRED",
                details={"offerKind": kind.value, "requiredPlan": PlanTier.PRO.value},
            )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _state(self, offer: Offer) -> OfferState:
        if not offer.is_active:
            return OfferState.DRAFT
        now = self._now()
        if self._is_after(offer.starts_at, now):
            return OfferState.SCHEDULED
        if offer.ends_at is not None and not self._is_after(offer.ends_at, now):
            return OfferState.EXPIRED
        return OfferState.LIVE

    def _is_after(self, moment: datetime | None, now: datetime) -> bool:
        if moment is None:
            return False
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment > now

    def _to_response(self, offer: Offer) -> OfferResponse:
        return OfferResponse(
            id=offer.id,
            restaurant_id=offer.restaurant_id,
            kind=offer.kind,
            title=offer.title,
            description=offer.description,
            terms=offer.terms,
            image_url=offer.image_url,
            coupon_code=offer.coupon_code,
            value=offer.value,
            starts_at=offer.starts_at,
            ends_at=offer.ends_at,
            is_active=offer.is_active,
            sort_order=offer.sort_order,
            state=self._state(offer),
        )
