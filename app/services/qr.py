from __future__ import annotations

import uuid
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ForbiddenError
from app.core.plans import spec_for
from app.models.enums import QrKind
from app.models.qr_code import QrCode
from app.repositories.qr_code import QrCodeRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.qr import CreateQrRequest
from app.services.restaurant import RestaurantService
from app.services.subscription import SubscriptionService
from app.utils.qr import generate_qr_data_url


class QRCodeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.restaurants = RestaurantRepository(session)
        self.qr_codes = QrCodeRepository(session)
        self.restaurant_service = RestaurantService(session)

    def _build_target_url(self, slug: str, table_number: str | None) -> str:
        base = settings.customer_app_base_url.rstrip("/")
        table = (table_number or "").strip()
        url = f"{base}/r/{slug}/menu"
        if table:
            url = f"{url}?{urlencode({'table': table})}"
        return url

    def _build_review_url(self, slug: str) -> str:
        base = settings.customer_app_base_url.rstrip("/")
        return f"{base}/r/{slug}/review"

    async def create(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID, payload: CreateQrRequest
    ) -> QrCode:
        restaurant = await self.restaurant_service.get_owned(restaurant_id, tenant_id)
        await self._assert_table_quota(restaurant.id)
        target_url = self._build_target_url(restaurant.slug, payload.table_number)
        qr = QrCode(
            restaurant_id=restaurant.id,
            label=payload.label,
            table_number=payload.table_number,
            target_url=target_url,
            image_data_url=generate_qr_data_url(target_url),
            kind=QrKind.TABLE,
        )
        self.session.add(qr)
        await self.session.commit()
        await self.session.refresh(qr)
        return qr

    async def _assert_table_quota(self, restaurant_id: uuid.UUID) -> None:
        """Gate *new* table QRs only.

        Existing table QRs keep resolving after a downgrade — a diner already
        seated at table 11 must never hit a paywall (PRD §22, resolved in favour
        of the customer path).
        """
        subscription = await SubscriptionService(self.session).get_or_create(restaurant_id)
        limit = spec_for(subscription.effective_plan).table_limit
        if limit is None:
            return
        existing = await self.qr_codes.count_tables(restaurant_id)
        if existing >= limit:
            raise ForbiddenError(
                f"The Basic plan covers up to {limit} tables. Upgrade to Pro for unlimited tables.",
                code="PLAN_LIMIT_REACHED",
                details={"limit": limit, "current": existing, "requiredPlan": "PRO"},
            )

    async def list_for_restaurant(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[QrCode]:
        await self.restaurant_service.get_owned(restaurant_id, tenant_id)
        result = await self.session.execute(
            select(QrCode)
            .where(QrCode.restaurant_id == restaurant_id)
            .order_by(QrCode.kind.desc(), QrCode.created_at)
        )
        return list(result.scalars().all())

    async def get_or_create_review_qr(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> QrCode:
        restaurant = await self.restaurant_service.get_owned(restaurant_id, tenant_id)
        result = await self.session.execute(
            select(QrCode).where(
                QrCode.restaurant_id == restaurant.id,
                QrCode.kind == QrKind.REVIEW,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        target_url = self._build_review_url(restaurant.slug)
        qr = QrCode(
            restaurant_id=restaurant.id,
            label="Reviews",
            table_number=None,
            target_url=target_url,
            image_data_url=generate_qr_data_url(target_url),
            kind=QrKind.REVIEW,
        )
        self.session.add(qr)
        await self.session.commit()
        await self.session.refresh(qr)
        return qr


def get_qr_service(session: AsyncSession) -> QRCodeService:
    return QRCodeService(session)
