from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.offer import CreateOfferRequest, OfferResponse, UpdateOfferRequest
from app.services.offer import OfferService

router = APIRouter(prefix="/restaurants/{restaurant_id}/offers", tags=["offers"])

_manager = require_roles(UserRole.OWNER, UserRole.MANAGER)


@router.get("", response_model=list[OfferResponse])
async def list_offers(restaurant: OwnedRestaurant, db: DBSession) -> list[OfferResponse]:
    return await OfferService(db).list_for_restaurant(restaurant.id)


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
async def create_offer(
    payload: CreateOfferRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    user: User = Depends(_manager),
) -> OfferResponse:
    return await OfferService(db).create(
        restaurant.id,
        payload,
        elevate_pro=user.is_super_admin,
    )


@router.patch("/{offer_id}", response_model=OfferResponse)
async def update_offer(
    offer_id: uuid.UUID,
    payload: UpdateOfferRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    user: User = Depends(_manager),
) -> OfferResponse:
    return await OfferService(db).update(
        offer_id,
        restaurant.id,
        payload,
        elevate_pro=user.is_super_admin,
    )


@router.delete("/{offer_id}", response_model=Message)
async def delete_offer(
    offer_id: uuid.UUID,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_manager),
) -> Message:
    await OfferService(db).delete(offer_id, restaurant.id)
    return Message(message="Offer deleted.")
