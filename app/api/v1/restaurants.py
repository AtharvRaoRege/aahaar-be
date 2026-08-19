from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.errors import ServiceUnavailableError
from app.dependencies.auth import require_approved, require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.restaurant import (
    CreateRestaurantRequest,
    PublishReadinessResponse,
    PublishRestaurantRequest,
    RestaurantResponse,
    UpdateRestaurantRequest,
)
from app.services.restaurant import RestaurantService
from app.services.storage import (
    MAX_UPLOAD_BYTES,
    StorageNotConfiguredError,
    upload_venue_logo,
)

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=list[RestaurantResponse])
async def list_restaurants(
    db: DBSession,
    user: User = Depends(require_approved),
) -> list[RestaurantResponse]:
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


@router.post("/{restaurant_id}/logo", response_model=RestaurantResponse)
async def upload_logo(
    restaurant: OwnedRestaurant,
    db: DBSession,
    file: UploadFile = File(...),
    _: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> RestaurantResponse:
    """Store the venue's logo and point the venue at it.

    Read one byte past the limit so an oversized upload is rejected on the size we
    measured rather than on whatever the client claimed in its headers.
    """
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        url = upload_venue_logo(restaurant.id, file.content_type or "", payload)
    except StorageNotConfiguredError as exc:
        raise ServiceUnavailableError(
            "Logo uploads need SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to be set.",
            code="STORAGE_NOT_CONFIGURED",
        ) from exc
    updated = await RestaurantService(db).set_logo_url(restaurant.id, url)
    return RestaurantResponse.model_validate(updated)


@router.get("/{restaurant_id}/publish-readiness", response_model=PublishReadinessResponse)
async def get_publish_readiness(
    restaurant: OwnedRestaurant,
    db: DBSession,
) -> PublishReadinessResponse:
    return await RestaurantService(db).publish_readiness(restaurant)


@router.post("/{restaurant_id}/publish", response_model=RestaurantResponse)
async def publish_restaurant(
    payload: PublishRestaurantRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(require_roles(UserRole.OWNER, UserRole.MANAGER)),
) -> RestaurantResponse:
    updated = await RestaurantService(db).publish(restaurant, payload.is_published)
    return RestaurantResponse.model_validate(updated)


@router.delete("/{restaurant_id}", response_model=Message)
async def delete_restaurant(
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(require_roles(UserRole.OWNER)),
) -> Message:
    await RestaurantService(db).delete(restaurant.id, restaurant.tenant_id)
    return Message(message="Restaurant deleted.")
