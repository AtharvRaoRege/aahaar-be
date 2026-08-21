from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.qr import CreateQrRequest, QrResponse
from app.services.qr import QRCodeService

router = APIRouter(prefix="/restaurants/{restaurant_id}/qr", tags=["qr"])


@router.post("", response_model=QrResponse, status_code=status.HTTP_201_CREATED)
async def create_qr(
    payload: CreateQrRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> QrResponse:
    qr = await QRCodeService(db).create_for_restaurant(
        restaurant,
        payload,
        elevate_pro=user.is_super_admin,
    )
    return QrResponse.model_validate(qr)


@router.get("/review", response_model=QrResponse)
async def get_review_qr(restaurant: OwnedRestaurant, db: DBSession) -> QrResponse:
    qr = await QRCodeService(db).get_or_create_review_qr_for(restaurant)
    return QrResponse.model_validate(qr)


@router.get("", response_model=list[QrResponse])
async def list_qr(restaurant: OwnedRestaurant, db: DBSession) -> list[QrResponse]:
    codes = await QRCodeService(db).list_for_restaurant_id(restaurant.id)
    return [QrResponse.model_validate(c) for c in codes]
