from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.core.vapid import vapid_claims, vapid_private_pem, vapid_public_key
from app.models.push_subscription import PushSubscription
from app.repositories.push import PushSubscriptionRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.push import SubscribePushRequest, VapidPublicKeyResponse

logger = get_logger("aahaar.push")


class PushService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.subscriptions = PushSubscriptionRepository(session)
        self.restaurants = RestaurantRepository(session)

    def public_key(self) -> VapidPublicKeyResponse:
        return VapidPublicKeyResponse(public_key=vapid_public_key())

    async def subscribe(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        payload: SubscribePushRequest,
        *,
        allow_cross_tenant: bool = False,
    ) -> None:
        restaurant = (
            await self.restaurants.get(payload.restaurant_id)
            if allow_cross_tenant
            else await self.restaurants.get_for_tenant(payload.restaurant_id, tenant_id)
        )
        if restaurant is None:
            raise NotFoundError("Restaurant not found.")
        endpoint = str(payload.subscription.endpoint)
        existing = await self.subscriptions.get_for_user(user_id, restaurant.id, endpoint)
        if existing is None:
            self.subscriptions.add(
                PushSubscription(
                    user_id=user_id,
                    restaurant_id=restaurant.id,
                    endpoint=endpoint,
                    p256dh=payload.subscription.keys.p256dh,
                    auth=payload.subscription.keys.auth,
                )
            )
        else:
            existing.p256dh = payload.subscription.keys.p256dh
            existing.auth = payload.subscription.keys.auth
        await self.session.commit()

    async def unsubscribe(self, user_id: uuid.UUID, endpoint: str) -> None:
        await self.subscriptions.delete_by_endpoint(user_id, endpoint)
        await self.session.commit()

    async def send_to_restaurant(self, restaurant_id: uuid.UUID, payload: dict[str, Any]) -> None:
        rows = await self.subscriptions.list_for_restaurant(restaurant_id)
        if not rows:
            return
        body = json.dumps(payload)
        private_key = vapid_private_pem()
        claims = vapid_claims()

        async def _one(row: PushSubscription) -> PushSubscription | None:
            try:
                await asyncio.to_thread(_send_one, row, body, private_key, claims)
                return None
            except Exception as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {404, 410}:
                    return row
                logger.warning("Web push failed endpoint=%s status=%s", row.endpoint[:48], status)
                return None

        results = await asyncio.gather(*(_one(row) for row in rows))
        stale = [row for row in results if row is not None]
        for row in stale:
            await self.subscriptions.delete(row)
        if stale:
            await self.session.commit()


def _send_one(row: PushSubscription, body: str, private_key: str, claims: dict[str, str]) -> None:
    from pywebpush import webpush

    webpush(
        subscription_info={
            "endpoint": row.endpoint,
            "keys": {"p256dh": row.p256dh, "auth": row.auth},
        },
        data=body,
        vapid_private_key=private_key,
        vapid_claims=claims,
        ttl=3600,
    )
