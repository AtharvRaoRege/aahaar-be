from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import OrderStatus
from app.models.review import Review
from app.repositories.order import OrderRepository
from app.repositories.restaurant import RestaurantRepository
from app.repositories.review import ReviewRepository
from app.schemas.common import Page, PageParams
from app.schemas.review import CreateReviewRequest, ReviewResponse, ReviewSummaryResponse
from app.services.notification import NotificationService

logger = get_logger("aahaar.reviews")


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reviews = ReviewRepository(session)
        self.orders = OrderRepository(session)
        self.restaurants = RestaurantRepository(session)

    def _clean(self, value: str | None) -> str | None:
        text = (value or "").strip()
        return text or None

    async def create_public(self, slug: str, payload: CreateReviewRequest) -> ReviewResponse:
        restaurant = await self.restaurants.get_by_slug(slug)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found.")

        order_id = payload.order_id
        if order_id is not None:
            order = await self.orders.get_with_relations(order_id)
            if order is None or order.restaurant_id != restaurant.id:
                raise NotFoundError("Order not found.")
            if order.status != OrderStatus.COMPLETED:
                raise ValidationError("You can rate after the order is completed.")
            if order.review is not None:
                raise ConflictError("This order already has a review.")

        review = Review(
            restaurant_id=restaurant.id,
            order_id=order_id,
            rating=payload.rating,
            comment=self._clean(payload.comment),
            improvement=self._clean(payload.improvement),
        )
        self.reviews.add(review)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("This order already has a review.") from exc
        await self.session.refresh(review)
        try:
            await NotificationService(self.session).review_created(review)
        except Exception:
            logger.exception("Review notify failed for %s", review.id)
        return ReviewResponse.model_validate(review)

    async def list_for_restaurant(
        self, restaurant_id: uuid.UUID, params: PageParams
    ) -> Page[ReviewResponse]:
        items, total = await self.reviews.list_for_restaurant(restaurant_id, params)
        return Page.create([ReviewResponse.model_validate(item) for item in items], total, params)

    async def summary(self, restaurant_id: uuid.UUID) -> ReviewSummaryResponse:
        return await self.reviews.summary(restaurant_id)

    async def public_summary(self, slug: str) -> ReviewSummaryResponse:
        restaurant = await self.restaurants.get_by_slug(slug)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found.")
        return await self.reviews.summary(restaurant.id)
