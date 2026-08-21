"""Plan catalogue, entitlements, and the sell sheet.

Two separate concerns live here on purpose:

* ``features`` is the **entitlement set** — what the server actually gates on.
* ``includes`` is the **sell sheet** — the plain-language list a restaurant reads
  on the plan screen. It only ever names capabilities that are built and working,
  so the plan page never makes a claim the product cannot keep.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import PlanTier


class PlanFeature(enum.StrEnum):
    """Capabilities that can be gated behind a tier."""

    MENU_SCAN = "MENU_SCAN"
    ADVANCED_ANALYTICS = "ADVANCED_ANALYTICS"
    DISH_PERFORMANCE = "DISH_PERFORMANCE"
    UPSELL_ENGINE = "UPSELL_ENGINE"
    ALL_OFFER_TYPES = "ALL_OFFER_TYPES"
    UNLIMITED_TABLES = "UNLIMITED_TABLES"


# Everything Basic already does. These are display keys the dashboard translates;
# each one maps to shipped behaviour, not a roadmap item.
BASIC_INCLUDES: tuple[str, ...] = (
    "QR_MENU",
    "UNLIMITED_DISHES",
    "DISH_PHOTOS",
    "EXCEL_IMPORT",
    "TABLE_QR",
    "TABLE_ORDERING",
    "LIVE_ORDER_SCREEN",
    "ORDER_TRACKING",
    "ORDER_ALERTS",
    "GUEST_RATINGS",
    "BASIC_OFFERS",
    "UPI_AT_TABLE",
    "VENUE_PROFILE",
    "STAFF_ROLES",
    "BASIC_INSIGHTS",
    "INSTALLABLE_APP",
)

# What Pro adds on top. Kept as deltas — the plan screen shows Basic's list once
# and then only the difference, so the comparison stays readable at a glance.
PRO_INCLUDES: tuple[str, ...] = (
    "MENU_SCAN",
    "UNLIMITED_TABLES",
    "ADVANCED_INSIGHTS",
    "SAVINGS_COUNTER",
    "DISH_PERFORMANCE",
    "UPSELL_ENGINE",
    "ALL_OFFER_TYPES",
    "PRIORITY_SUPPORT",
)


@dataclass(frozen=True)
class PlanSpec:
    tier: PlanTier
    monthly_price: Decimal
    trial_days: int
    table_limit: int | None
    features: frozenset[PlanFeature]
    includes: tuple[str, ...]

    @property
    def unlimited_tables(self) -> bool:
        return self.table_limit is None


BASIC = PlanSpec(
    tier=PlanTier.BASIC,
    monthly_price=Decimal("750.00"),
    trial_days=90,
    table_limit=10,
    features=frozenset(),
    includes=BASIC_INCLUDES,
)

PRO = PlanSpec(
    tier=PlanTier.PRO,
    monthly_price=Decimal("1500.00"),
    trial_days=15,
    table_limit=None,
    features=frozenset(PlanFeature),
    includes=PRO_INCLUDES,
)

PLANS: dict[PlanTier, PlanSpec] = {PlanTier.BASIC: BASIC, PlanTier.PRO: PRO}

# Offer kinds a Basic kitchen may publish. Everything else needs Pro.
BASIC_OFFER_KINDS = frozenset({"PERCENT", "FLAT"})

# Billing period length in days. Monthly-only at launch (PRD §8).
BILLING_PERIOD_DAYS = 30

# Days of continued service after a failed renewal before suspension (PRD §22).
GRACE_PERIOD_DAYS = 3


def spec_for(tier: PlanTier) -> PlanSpec:
    return PLANS[tier]


def has_feature(tier: PlanTier, feature: PlanFeature) -> bool:
    return feature in PLANS[tier].features
