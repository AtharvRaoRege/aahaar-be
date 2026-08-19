from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analytics,
    auth,
    menu,
    offers,
    orders,
    public,
    push,
    qr,
    restaurants,
    reviews,
    subscriptions,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(restaurants.router)
api_router.include_router(subscriptions.router)
api_router.include_router(menu.router)
api_router.include_router(qr.router)
api_router.include_router(orders.router)
api_router.include_router(offers.router)
api_router.include_router(analytics.router)
api_router.include_router(reviews.router)
api_router.include_router(push.router)
api_router.include_router(public.router)
