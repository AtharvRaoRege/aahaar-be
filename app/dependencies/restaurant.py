from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Path

from app.core.errors import NotFoundError
from app.dependencies.auth import CurrentUser, assert_approved
from app.dependencies.db import DBSession
from app.models.restaurant import Restaurant
from app.repositories.restaurant import RestaurantRepository


async def get_owned_restaurant(
    db: DBSession,
    user: CurrentUser,
    restaurant_id: Annotated[uuid.UUID, Path(alias="restaurant_id")],
) -> Restaurant:
    """Resolve a restaurant from the path and enforce tenant ownership.

    Super admins may open any kitchen so they can inspect menus, orders, and QR.
    """
    assert_approved(user)
    repo = RestaurantRepository(db)
    if user.is_super_admin:
        restaurant = await repo.get(restaurant_id)
    else:
        restaurant = await repo.get_for_tenant(restaurant_id, user.tenant_id)
    if restaurant is None:
        raise NotFoundError("Restaurant not found.")
    return restaurant


OwnedRestaurant = Annotated[Restaurant, Depends(get_owned_restaurant)]


async def get_public_restaurant(
    db: DBSession,
    slug: Annotated[str, Path()],
) -> Restaurant:
    """Resolve an active restaurant from its public slug (no auth)."""
    restaurant = await RestaurantRepository(db).get_by_slug(slug)
    if restaurant is None or not restaurant.is_active:
        raise NotFoundError("Restaurant not found.")
    return restaurant


PublicRestaurant = Annotated[Restaurant, Depends(get_public_restaurant)]


async def get_serving_restaurant(
    db: DBSession,
    restaurant: PublicRestaurant,
) -> Restaurant:
    """Like ``PublicRestaurant``, but also requires the menu to be live.

    Used for every public endpoint that returns menu content or accepts an
    order. The profile endpoint stays ungated so the customer app can render the
    right "temporarily unavailable" copy instead of an error.
    """
    from app.services.public_state import resolve_serving_state

    is_serving, reason = await resolve_serving_state(db, restaurant)
    if not is_serving:
        raise NotFoundError(
            "This menu is temporarily unavailable.",
            code="MENU_UNAVAILABLE",
            details={"reason": reason},
        )
    return restaurant


ServingRestaurant = Annotated[Restaurant, Depends(get_serving_restaurant)]
