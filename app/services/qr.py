from __future__ import annotations

import uuid
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.qr_code import QrCode
from app.repositories.restaurant import RestaurantRepository
from app.schemas.qr import CreateQrRequest
from app.services.restaurant import RestaurantService
from app.utils.qr import generate_qr_data_url


class QRCodeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.restaurants = RestaurantRepository(session)
        self.restaurant_service = RestaurantService(session)

    def _build_target_url(self, slug: str, table_number: str | None) -> str:
        base = settings.customer_app_base_url.rstrip("/")
        table = (table_number or "").strip()
        url = f"{base}/r/{slug}/menu"
        if table:
            url = f"{url}?{urlencode({'table': table})}"
        return url

    async def create(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID, payload: CreateQrRequest
    ) -> QrCode:
        restaurant = await self.restaurant_service.get_owned(restaurant_id, tenant_id)
        target_url = self._build_target_url(restaurant.slug, payload.table_number)
        qr = QrCode(
            restaurant_id=restaurant.id,
            label=payload.label,
            table_number=payload.table_number,
            target_url=target_url,
            image_data_url=generate_qr_data_url(target_url),
        )
        self.session.add(qr)
        await self.session.commit()
        await self.session.refresh(qr)
        return qr

    async def list_for_restaurant(
        self, restaurant_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> list[QrCode]:
        await self.restaurant_service.get_owned(restaurant_id, tenant_id)
        result = await self.session.execute(
            select(QrCode).where(QrCode.restaurant_id == restaurant_id).order_by(QrCode.created_at)
        )
        return list(result.scalars().all())


def get_qr_service(session: AsyncSession) -> QRCodeService:
    return QRCodeService(session)
