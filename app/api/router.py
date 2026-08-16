from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, menu, orders, public, qr, restaurants

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(restaurants.router)
api_router.include_router(menu.router)
api_router.include_router(qr.router)
api_router.include_router(orders.router)
api_router.include_router(public.router)
