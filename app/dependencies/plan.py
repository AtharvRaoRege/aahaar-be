"""Plan entitlement gates.

Gating lives here, server-side, on the endpoints themselves — the dashboard only
mirrors it (PRD §34: RBAC and plan checks are never UI-only).

Super admins always resolve as Pro so they can exercise the full product while
operating any kitchen (including impersonation).
"""

from __future__ import annotations

from app.core.errors import ForbiddenError
from app.core.plans import PlanFeature, has_feature
from app.dependencies.auth import CurrentUser
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import PlanTier
from app.models.restaurant import Restaurant
from app.models.user import User
from app.services.subscription import SubscriptionService


def elevate_plan(plan: PlanTier, user: User | None) -> PlanTier:
    """Treat platform super admins as Pro for entitlement checks."""
    if user is not None and user.is_super_admin:
        return PlanTier.PRO
    return plan


async def get_effective_plan(
    restaurant: OwnedRestaurant,
    db: DBSession,
    user: CurrentUser,
) -> PlanTier:
    """The tier actually in force for this venue right now (Pro for super admins)."""
    subscription = await SubscriptionService(db).get_or_create(restaurant.id)
    return elevate_plan(subscription.effective_plan, user)


def require_feature(feature: PlanFeature):
    """Reject the request unless the venue's live plan includes ``feature``."""

    async def _checker(
        restaurant: OwnedRestaurant,
        db: DBSession,
        user: CurrentUser,
    ) -> Restaurant:
        if user.is_super_admin:
            return restaurant
        plan = await get_effective_plan(restaurant, db, user)
        if not has_feature(plan, feature):
            raise ForbiddenError(
                "This feature is part of the Pro plan.",
                code="PLAN_UPGRADE_REQUIRED",
                details={"feature": feature.value, "requiredPlan": PlanTier.PRO.value},
            )
        return restaurant

    return _checker
