from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.dependencies.rate_limit import rate_limit
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.review import CreateReviewRequest, ReviewResponse, ReviewSummaryResponse
from app.services.review import ReviewService

router = APIRouter(tags=["reviews"])


@router.post(
    "/public/restaurants/{slug}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_review(
    slug: str,
    payload: CreateReviewRequest,
    db: DBSession,
    _: None = Depends(rate_limit("public")),
) -> ReviewResponse:
    return await ReviewService(db).create_public(slug, payload)


@router.get(
    "/public/restaurants/{slug}/reviews/summary",
    response_model=ReviewSummaryResponse,
)
async def public_review_summary(slug: str, db: DBSession) -> ReviewSummaryResponse:
    return await ReviewService(db).public_summary(slug)


@router.get(
    "/restaurants/{restaurant_id}/reviews",
    response_model=Page[ReviewResponse],
)
async def list_reviews(
    restaurant: OwnedRestaurant,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    _: User = Depends(
        require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION, UserRole.KITCHEN)
    ),
) -> Page[ReviewResponse]:
    params = PageParams(page=page, page_size=page_size)
    return await ReviewService(db).list_for_restaurant(restaurant.id, params)


@router.get(
    "/restaurants/{restaurant_id}/reviews/summary",
    response_model=ReviewSummaryResponse,
)
async def review_summary(
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(
        require_roles(UserRole.OWNER, UserRole.MANAGER, UserRole.RECEPTION, UserRole.KITCHEN)
    ),
) -> ReviewSummaryResponse:
    return await ReviewService(db).summary(restaurant.id)
