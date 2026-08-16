"""FastAPI dependencies: DB session, auth/tenant resolution, rate limiting."""

from app.dependencies.auth import (
    CurrentUser,
    get_current_user,
    require_roles,
)
from app.dependencies.db import DBSession, get_db
from app.dependencies.rate_limit import rate_limit
from app.dependencies.restaurant import (
    OwnedRestaurant,
    get_owned_restaurant,
    get_public_restaurant,
)

__all__ = [
    "CurrentUser",
    "DBSession",
    "OwnedRestaurant",
    "get_current_user",
    "get_db",
    "get_owned_restaurant",
    "get_public_restaurant",
    "rate_limit",
    "require_roles",
]
