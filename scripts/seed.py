"""Seed the database with a demo tenant, staff, restaurant, and menu.

Idempotent: if the demo restaurant already exists, the script exits without
changes. Run with::

    python -m scripts.seed
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.core.database import SessionFactory
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.menu import Category, MenuItem
from app.models.restaurant import Restaurant
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.qr import CreateQrRequest
from app.services.qr import QRCodeService
from sqlalchemy import select

logger = get_logger("aahaar.seed")

DEMO_SLUG = "spice-garden"
DEMO_PASSWORD = "Password123!"

STAFF = [
    ("owner@aahaar.app", "Aarav Mehta", UserRole.OWNER),
    ("reception@aahaar.app", "Priya Nair", UserRole.RECEPTION),
    ("kitchen@aahaar.app", "Rahul Verma", UserRole.KITCHEN),
]

# (category, [(name, description, price, veg, vegan, spice)])
MENU: dict[str, list[tuple[str, str, str, bool, bool, int]]] = {
    "Starters": [
        ("Paneer Tikka", "Smoky grilled cottage cheese with peppers.", "280", True, False, 2),
        ("Chilli Gobi", "Crispy cauliflower tossed in a spicy garlic sauce.", "240", True, True, 3),
        ("Chicken 65", "Fiery South-Indian style fried chicken.", "320", False, False, 3),
    ],
    "Main Course": [
        (
            "Butter Chicken",
            "Tandoori chicken in a rich tomato-butter gravy.",
            "420",
            False,
            False,
            1,
        ),
        ("Paneer Butter Masala", "Cottage cheese in a creamy tomato gravy.", "360", True, False, 1),
        ("Dal Makhani", "Slow-cooked black lentils with cream.", "300", True, False, 1),
        ("Veg Biryani", "Fragrant basmati rice with spiced vegetables.", "320", True, True, 2),
    ],
    "Breads": [
        ("Butter Naan", "Soft leavened flatbread brushed with butter.", "60", True, False, 0),
        ("Garlic Naan", "Naan topped with garlic and coriander.", "80", True, False, 0),
        ("Tandoori Roti", "Whole-wheat flatbread from the clay oven.", "40", True, True, 0),
    ],
    "Drinks": [
        ("Masala Chai", "Spiced Indian milk tea.", "60", True, False, 0),
        ("Sweet Lassi", "Chilled sweet yogurt drink.", "90", True, False, 0),
        ("Fresh Lime Soda", "Zesty lime with soda, sweet or salted.", "80", True, True, 0),
    ],
    "Desserts": [
        ("Gulab Jamun", "Warm milk dumplings in rose syrup.", "120", True, False, 0),
        ("Gajar Ka Halwa", "Slow-cooked carrot pudding with nuts.", "150", True, False, 0),
    ],
}


async def seed() -> None:
    configure_logging(debug=True)
    async with SessionFactory() as db:
        existing = await db.execute(select(Restaurant).where(Restaurant.slug == DEMO_SLUG))
        if existing.scalar_one_or_none() is not None:
            logger.info("Demo data already present (%s). Nothing to do.", DEMO_SLUG)
            return

        tenant = Tenant(name="Spice Garden Group", slug="spice-garden-group")
        db.add(tenant)
        await db.flush()

        for email, name, role in STAFF:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email=email,
                    full_name=name,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    role=role,
                    is_active=True,
                )
            )

        restaurant = Restaurant(
            tenant_id=tenant.id,
            name="Spice Garden",
            slug=DEMO_SLUG,
            description="Modern Indian kitchen — bold flavours, fast service.",
            phone="+91 98765 43210",
            address="12 MG Road, Bengaluru",
            currency="INR",
        )
        db.add(restaurant)
        await db.flush()

        for order, (cat_name, items) in enumerate(MENU.items()):
            category = Category(restaurant_id=restaurant.id, name=cat_name, sort_order=order)
            db.add(category)
            await db.flush()
            for i, (name, desc, price, veg, vegan, spice) in enumerate(items):
                db.add(
                    MenuItem(
                        restaurant_id=restaurant.id,
                        category_id=category.id,
                        name=name,
                        description=desc,
                        base_price=Decimal(price),
                        is_available=True,
                        is_vegetarian=veg,
                        is_vegan=vegan,
                        spice_level=spice,
                        sort_order=i,
                    )
                )

        await db.commit()

        # A table QR that points at the customer app.
        await QRCodeService(db).create(
            restaurant.id, tenant.id, CreateQrRequest(label="Table 1", table_number="1")
        )

        logger.info("Seeded restaurant '%s' (slug=%s).", restaurant.name, DEMO_SLUG)
        logger.info("Login with any of:")
        for email, _, role in STAFF:
            logger.info("  %-24s / %s  (%s)", email, DEMO_PASSWORD, role.value)


if __name__ == "__main__":
    asyncio.run(seed())
