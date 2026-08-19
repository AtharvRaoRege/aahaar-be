from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.plans import PlanFeature
from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.dependencies.plan import require_feature
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.analytics import AnalyticsSummary, DishPerformanceResponse
from app.services.analytics import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS, AnalyticsService

router = APIRouter(prefix="/restaurants/{restaurant_id}/analytics", tags=["analytics"])

_viewer = require_roles(UserRole.OWNER, UserRole.MANAGER)
_dish_performance = require_feature(PlanFeature.DISH_PERFORMANCE)


@router.get("/summary", response_model=AnalyticsSummary)
async def get_summary(
    restaurant: OwnedRestaurant,
    db: DBSession,
    range_days: int = Query(default=DEFAULT_RANGE_DAYS, ge=1, le=MAX_RANGE_DAYS, alias="rangeDays"),
    _: User = Depends(_viewer),
) -> AnalyticsSummary:
    return await AnalyticsService(db).summary(restaurant.id, range_days)


@router.get("/dishes", response_model=DishPerformanceResponse)
async def get_dish_performance(
    db: DBSession,
    restaurant: Restaurant = Depends(_dish_performance),
    range_days: int = Query(default=DEFAULT_RANGE_DAYS, ge=1, le=MAX_RANGE_DAYS, alias="rangeDays"),
    _: User = Depends(_viewer),
) -> DishPerformanceResponse:
    return await AnalyticsService(db).dish_performance(restaurant.id, range_days)
