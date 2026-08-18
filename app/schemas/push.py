from __future__ import annotations

import uuid

from pydantic import Field

from app.schemas.common import CamelModel


class PushKeys(CamelModel):
    p256dh: str = Field(min_length=8, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class PushSubscriptionPayload(CamelModel):
    endpoint: str = Field(min_length=8, max_length=2048)
    keys: PushKeys


class SubscribePushRequest(CamelModel):
    restaurant_id: uuid.UUID
    subscription: PushSubscriptionPayload


class UnsubscribePushRequest(CamelModel):
    endpoint: str = Field(min_length=8, max_length=2048)


class VapidPublicKeyResponse(CamelModel):
    public_key: str
