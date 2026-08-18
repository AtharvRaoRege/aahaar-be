from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.review import Review
from app.repositories.base import BaseRepository
from app.schemas.common import PageParams
from app.schemas.review import ReviewSummaryResponse


class ReviewRepository(BaseRepository[Review]):
    model = Review

    async def list_for_restaurant(
        self, restaurant_id: uuid.UUID, params: PageParams
    ) -> tuple[list[Review], int]:
        conditions = [Review.restaurant_id == restaurant_id]
        count_result = await self.session.execute(
            select(func.count()).select_from(Review).where(*conditions)
        )
        total = int(count_result.scalar_one())
        result = await self.session.execute(
            select(Review)
            .where(*conditions)
            .order_by(Review.created_at.desc())
            .limit(params.page_size)
            .offset(params.offset)
        )
        return list(result.scalars().all()), total

    async def summary(self, restaurant_id: uuid.UUID) -> ReviewSummaryResponse:
        avg_result = await self.session.execute(
            select(func.avg(Review.rating), func.count(Review.id)).where(
                Review.restaurant_id == restaurant_id
            )
        )
        average, count = avg_result.one()
        dist_result = await self.session.execute(
            select(Review.rating, func.count(Review.id))
            .where(Review.restaurant_id == restaurant_id)
            .group_by(Review.rating)
        )
        distribution = {str(star): 0 for star in range(1, 6)}
        for rating, star_count in dist_result.all():
            distribution[str(int(rating))] = int(star_count)
        total = int(count or 0)
        avg = round(float(average), 1) if average is not None else 0.0
        return ReviewSummaryResponse(average=avg, count=total, distribution=distribution)
