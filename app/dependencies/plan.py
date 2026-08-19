"""Plan entitlement gates.

Gating lives here, server-side, on the endpoints themselves — the dashboard only
mirrors it (PRD §34: RBAC and plan checks are never UI-only).
"""

from __future__ import annotations

from app.core.errors import ForbiddenError
from app.core.plans import PlanFeature, has_feature
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import PlanTier
from app.models.restaurant import Restaurant
from app.services.subscription import SubscriptionService


async def get_effective_plan(restaurant: OwnedRestaurant, db: DBSession) -> PlanTier:
    """The tier actually in force for this venue right now."""
    subscription = await SubscriptionService(db).get_or_create(restaurant.id)
    return subscription.effective_plan


def require_feature(feature: PlanFeature):
    """Reject the request unless the venue's live plan includes ``feature``."""

    async def _checker(restaurant: OwnedRestaurant, db: DBSession) -> Restaurant:
        plan = await get_effective_plan(restaurant, db)
        if not has_feature(plan, feature):
            raise ForbiddenError(
                "This feature is part of the Pro plan.",
                code="PLAN_UPGRADE_REQUIRED",
                details={"feature": feature.value, "requiredPlan": PlanTier.PRO.value},
            )
        return restaurant

    return _checker
