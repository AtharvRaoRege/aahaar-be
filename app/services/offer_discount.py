"""Coupon discount math for live offers.

PERCENT / FLAT / BOGO can reduce the bill. Other kinds stay informational
unless they also carry a percent/flat ``value``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import ValidationError
from app.models.enums import OfferKind
from app.models.offer import Offer

TWOPLACES = Decimal("0.01")


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def compute_discount(
    offer: Offer,
    *,
    subtotal: Decimal,
    units: list[Decimal],
) -> Decimal:
    """Return a discount capped at ``subtotal``. ``units`` are per-plate prices."""
    count = len(units)
    if count < max(1, offer.min_item_count):
        raise ValidationError(
            f"Add at least {offer.min_item_count} items to use this offer.",
            code="OFFER_MIN_ITEMS",
            details={"minItemCount": offer.min_item_count, "itemCount": count},
        )
    minimum = _money(offer.min_order_amount or 0)
    if subtotal < minimum:
        raise ValidationError(
            f"Spend at least ₹{minimum} to use this offer.",
            code="OFFER_MIN_ORDER",
            details={"minOrderAmount": str(minimum), "subtotal": str(subtotal)},
        )

    discount = Decimal("0")
    if offer.kind == OfferKind.PERCENT:
        if offer.value is None:
            raise ValidationError("This offer has no discount amount.", code="OFFER_NO_VALUE")
        discount = _money(subtotal * (offer.value / Decimal("100")))
    elif offer.kind == OfferKind.FLAT:
        if offer.value is None:
            raise ValidationError("This offer has no discount amount.", code="OFFER_NO_VALUE")
        discount = _money(offer.value)
    elif offer.kind == OfferKind.BOGO:
        if count < 2:
            raise ValidationError(
                "Add at least 2 items for buy-one-get-one.",
                code="OFFER_MIN_ITEMS",
                details={"minItemCount": 2, "itemCount": count},
            )
        discount = _money(min(units))
    elif offer.value is not None and offer.kind in {
        OfferKind.COMBO,
        OfferKind.HAPPY_HOUR,
        OfferKind.SPECIAL_DAY,
    }:
        discount = _money(offer.value)
    else:
        raise ValidationError(
            "This offer cannot be applied at checkout. Ask staff for help.",
            code="OFFER_NOT_APPLICABLE",
        )

    if discount <= 0:
        raise ValidationError("This offer does not reduce the bill.", code="OFFER_NO_VALUE")
    return min(discount, _money(subtotal))
