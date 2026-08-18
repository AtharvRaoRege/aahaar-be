"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``create_all`` can see the full schema.
"""

from app.models.customer_session import CustomerSession
from app.models.enums import OrderStatus, QrKind, UserRole
from app.models.menu import (
    Category,
    MenuItem,
    MenuItemAddon,
    MenuItemVariant,
)
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.push_subscription import PushSubscription
from app.models.qr_code import QrCode
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.tenant import Tenant
from app.models.user import RefreshToken, User

__all__ = [
    "Category",
    "CustomerSession",
    "MenuItem",
    "MenuItemAddon",
    "MenuItemVariant",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusHistory",
    "PushSubscription",
    "QrCode",
    "QrKind",
    "RefreshToken",
    "Restaurant",
    "Review",
    "Tenant",
    "User",
    "UserRole",
]
