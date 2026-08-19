"""Whether a venue's public menu is currently serving diners.

Kept separate from ``RestaurantService`` because both the public profile endpoint
and the QR routing layer need the same answer, and neither should own it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionStatus
from app.models.restaurant import Restaurant
from app.repositories.subscription import SubscriptionRepository

REASON_NOT_PUBLISHED = "NOT_PUBLISHED"
REASON_SUSPENDED = "SUSPENDED"


async def resolve_serving_state(
    session: AsyncSession, restaurant: Restaurant
) -> tuple[bool, str | None]:
    """(is_serving, reason). Reason is ``None`` while the menu is live."""
    if not restaurant.is_published:
        return False, REASON_NOT_PUBLISHED

    subscription = await SubscriptionRepository(session).get_for_restaurant(restaurant.id)
    if subscription is not None and subscription.status in {
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.CANCELLED,
    }:
        # Data is retained and the QR keeps resolving — only the menu is hidden.
        return False, REASON_SUSPENDED

    return True, None
