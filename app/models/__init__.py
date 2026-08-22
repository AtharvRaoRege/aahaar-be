"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``create_all`` can see the full schema.
"""

from app.models.analytics import AnalyticsEvent
from app.models.customer_session import CustomerSession
from app.models.enums import (
    AnalyticsEventType,
    OfferKind,
    OfferState,
    OrderStatus,
    PlanRequestStatus,
    PlanTier,
    QrKind,
    SubscriptionStatus,
    UserRole,
)
from app.models.menu import (
    Category,
    MenuItem,
    MenuItemAddon,
    MenuItemUpsell,
    MenuItemVariant,
)
from app.models.offer import Offer
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.plan_request import PlanRequest
from app.models.platform_setting import PlatformSetting
from app.models.push_subscription import PushSubscription
from app.models.qr_code import QrCode
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.subscription import Subscription
from app.models.tenant import Tenant
from app.models.user import RefreshToken, User
from app.models.waiter_call import WaiterCall

__all__ = [
    "AnalyticsEvent",
    "AnalyticsEventType",
    "Category",
    "CustomerSession",
    "MenuItem",
    "MenuItemAddon",
    "MenuItemUpsell",
    "MenuItemVariant",
    "Offer",
    "OfferKind",
    "OfferState",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusHistory",
    "PlanRequest",
    "PlanRequestStatus",
    "PlanTier",
    "PlatformSetting",
    "PushSubscription",
    "QrCode",
    "QrKind",
    "RefreshToken",
    "Restaurant",
    "Review",
    "Subscription",
    "SubscriptionStatus",
    "Tenant",
    "User",
    "UserRole",
    "WaiterCall",
]
