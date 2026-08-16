from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import CurrentUser, require_approved, require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.restaurant import (
    CreateRestaurantRequest,
    RestaurantResponse,
    UpdateRestaurantRequest,
)
from app.services.restaurant import RestaurantService

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=list[RestaurantResponse])
async def list_restaurants(db: DBSession, user: CurrentUser) -> list[RestaurantResponse]:
    restaurants = await RestaurantService(db).list_for_tenant(user.tenant_id)
    return [RestaurantResponse.model_validate(r) for r in restaurants]


@router.post("", response_model=RestaurantResponse, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    payload: CreateRestaurantRequest,
    db: DBSession,
    user: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
    __: User = Depends(require_approved),
) -> RestaurantResponse:
    restaurant = await RestaurantService(db).create(user.tenant_id, payload)
    return RestaurantResponse.model_validate(restaurant)


@router.get("/{restaurant_id}", response_model=RestaurantResponse)
async def get_restaurant(restaurant: OwnedRestaurant) -> RestaurantResponse:
    return RestaurantResponse.model_validate(restaurant)


@router.patch("/{restaurant_id}", response_model=RestaurantResponse)
async def update_restaurant(
    payload: UpdateRestaurantRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> RestaurantResponse:
    updated = await RestaurantService(db).update(restaurant.id, restaurant.tenant_id, payload)
    return RestaurantResponse.model_validate(updated)


@router.delete("/{restaurant_id}", response_model=Message)
async def delete_restaurant(
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(require_roles(UserRole.OWNER)),
) -> Message:
    await RestaurantService(db).delete(restaurant.id, restaurant.tenant_id)
    return Message(message="Restaurant deleted.")
