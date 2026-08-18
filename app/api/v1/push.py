from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.push import SubscribePushRequest, UnsubscribePushRequest, VapidPublicKeyResponse
from app.services.push import PushService

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-key", response_model=VapidPublicKeyResponse)
async def get_vapid_key(
    db: DBSession,
    _: User = Depends(
        require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION, UserRole.KITCHEN)
    ),
) -> VapidPublicKeyResponse:
    return PushService(db).public_key()


@router.post("/subscriptions", response_model=Message, status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    payload: SubscribePushRequest,
    db: DBSession,
    user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION, UserRole.KITCHEN)
    ),
) -> Message:
    await PushService(db).subscribe(
        user.id,
        user.tenant_id,
        payload,
        allow_cross_tenant=user.is_super_admin,
    )
    return Message(message="Alerts enabled on this device.")


@router.post("/unsubscribe", response_model=Message)
async def unsubscribe_push(
    payload: UnsubscribePushRequest,
    db: DBSession,
    user: User = Depends(
        require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION, UserRole.KITCHEN)
    ),
) -> Message:
    await PushService(db).unsubscribe(user.id, str(payload.endpoint))
    return Message(message="Alerts turned off on this device.")
