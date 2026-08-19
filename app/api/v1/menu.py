from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response

from app.dependencies.auth import require_roles
from app.dependencies.db import DBSession
from app.dependencies.restaurant import OwnedRestaurant
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.menu import (
    CategoryResponse,
    CreateCategoryRequest,
    CreateMenuItemRequest,
    ImportJobResponse,
    MenuItemResponse,
    MenuResponse,
    SetUpsellsRequest,
    UpdateCategoryRequest,
    UpdateMenuItemRequest,
    UpsellsResponse,
)

# Menu scanning (OCR) is switched off. Re-enabling also needs these back on the
# import lines above: PlanFeature from app.core.plans, require_feature from
# app.dependencies.plan, and Restaurant from app.models.restaurant.
# These imports stay commented because
# app.services.menu_scan imports pytesseract at module level, which is no longer
# installed — importing it would take the whole API down at startup.
# from app.schemas.menu_scan import (
#     ApplyMenuScanRequest,
#     ApplyMenuScanResponse,
#     MenuScanResponse,
# )
from app.services import menu_import
from app.services.menu import MenuService

# from app.services.menu_scan import MAX_UPLOAD_BYTES, MenuScanService

router = APIRouter(tags=["menu"])

_manager = require_roles(UserRole.OWNER, UserRole.MANAGER)
# _scan = require_feature(PlanFeature.MENU_SCAN)


# ── Full menu (dashboard, all items) ─────────────────────────
@router.get("/restaurants/{restaurant_id}/menu", response_model=MenuResponse)
async def get_menu(restaurant: OwnedRestaurant, db: DBSession) -> MenuResponse:
    return await MenuService(db).get_menu(restaurant.id, public=False)


@router.get("/restaurants/{restaurant_id}/menu/import-template")
async def download_import_template(
    restaurant: OwnedRestaurant,
    _: User = Depends(_manager),
) -> Response:
    _ = restaurant.id
    return Response(
        content=menu_import.build_template_xlsx(),
        media_type=menu_import.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{menu_import.TEMPLATE_FILENAME}"'},
    )


@router.post(
    "/restaurants/{restaurant_id}/menu/import",
    response_model=ImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_menu(
    restaurant: OwnedRestaurant,
    file: UploadFile = File(...),
    _: User = Depends(_manager),
) -> ImportJobResponse:
    menu_import.validate_upload(file.filename, getattr(file, "size", None))
    payload = await file.read()
    await file.close()
    job = await menu_import.start_import(restaurant.id, payload)
    return job.to_response()


@router.get(
    "/restaurants/{restaurant_id}/menu/import/{job_id}",
    response_model=ImportJobResponse,
)
async def get_import_job(
    job_id: uuid.UUID,
    restaurant: OwnedRestaurant,
    _: User = Depends(_manager),
) -> ImportJobResponse:
    job = await menu_import.get_job(job_id, restaurant.id)
    return job.to_response()


# ── Categories ───────────────────────────────────────────────
@router.post(
    "/restaurants/{restaurant_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: CreateCategoryRequest,
    restaurant: OwnedRestaurant,
    db: DBSession,
    _: User = Depends(_manager),
) -> CategoryResponse:
    category = await MenuService(db).create_category(restaurant.id, payload)
    return CategoryResponse.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: uuid.UUID,
    payload: UpdateCategoryRequest,
    db: DBSession,
    user: User = Depends(_manager),
) -> CategoryResponse:
    category = await MenuService(db).update_category(
        category_id,
        user.tenant_id,
        payload,
        allow_cross_tenant=user.is_super_admin,
    )
    return CategoryResponse.model_validate(category)


@router.delete("/categories/{category_id}", response_model=Message)
async def delete_category(
    category_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(_manager),
) -> Message:
    await MenuService(db).delete_category(
        category_id, user.tenant_id, allow_cross_tenant=user.is_super_admin
    )
    return Message(message="Category deleted.")


# ── Menu items ───────────────────────────────────────────────
@router.post(
    "/categories/{category_id}/items",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_menu_item(
    category_id: uuid.UUID,
    payload: CreateMenuItemRequest,
    db: DBSession,
    user: User = Depends(_manager),
) -> MenuItemResponse:
    item = await MenuService(db).create_item(
        category_id,
        user.tenant_id,
        payload,
        allow_cross_tenant=user.is_super_admin,
    )
    return MenuItemResponse.model_validate(item)


@router.patch("/menu-items/{menu_item_id}", response_model=MenuItemResponse)
async def update_menu_item(
    menu_item_id: uuid.UUID,
    payload: UpdateMenuItemRequest,
    db: DBSession,
    user: User = Depends(_manager),
) -> MenuItemResponse:
    item = await MenuService(db).update_item(
        menu_item_id,
        user.tenant_id,
        payload,
        allow_cross_tenant=user.is_super_admin,
    )
    return MenuItemResponse.model_validate(item)


@router.delete("/menu-items/{menu_item_id}", response_model=Message)
async def delete_menu_item(
    menu_item_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(_manager),
) -> Message:
    await MenuService(db).delete_item(
        menu_item_id, user.tenant_id, allow_cross_tenant=user.is_super_admin
    )
    return Message(message="Menu item deleted.")


# ── Upsell pairings (Pro) ────────────────────────────────────
@router.get("/menu-items/{menu_item_id}/upsells", response_model=UpsellsResponse)
async def get_menu_item_upsells(
    menu_item_id: uuid.UUID,
    db: DBSession,
    user: User = Depends(_manager),
) -> UpsellsResponse:
    return await MenuService(db).upsells_for_owner(
        menu_item_id, user.tenant_id, allow_cross_tenant=user.is_super_admin
    )


@router.put("/menu-items/{menu_item_id}/upsells", response_model=UpsellsResponse)
async def set_menu_item_upsells(
    menu_item_id: uuid.UUID,
    payload: SetUpsellsRequest,
    db: DBSession,
    user: User = Depends(_manager),
) -> UpsellsResponse:
    return await MenuService(db).set_upsells(
        menu_item_id,
        user.tenant_id,
        payload,
        allow_cross_tenant=user.is_super_admin,
    )


# ── Menu scanning (Pro) — SWITCHED OFF ───────────────────────
#
# OCR is not in use. The service and schemas are still on disk
# (app/services/menu_scan.py, app/schemas/menu_scan.py) so re-enabling is:
#   1. uncomment pytesseract and pypdf in requirements.txt
#   2. put tesseract-ocr back on the apt line in the Dockerfile
#   3. uncomment the imports, _scan and the two routes here
#   4. uncomment "MENU_SCAN" in PRO_INCLUDES (app/core/plans.py)
#   5. uncomment the scan buttons and sheet in the dashboard menu page
#
# @router.post(
#     "/restaurants/{restaurant_id}/menu/scan",
#     response_model=MenuScanResponse,
# )
# async def scan_menu_image(
#     db: DBSession,
#     restaurant: Restaurant = Depends(_scan),
#     file: UploadFile = File(...),
#     _: User = Depends(_manager),
# ) -> MenuScanResponse:
#     """Read a menu photo or PDF into reviewable rows. Writes nothing."""
#     payload = await file.read(MAX_UPLOAD_BYTES + 1)
#     return await MenuScanService(db).scan(
#         restaurant.id,
#         file.filename or "",
#         file.content_type or "",
#         payload,
#     )
#
#
# @router.post(
#     "/restaurants/{restaurant_id}/menu/scan/apply",
#     response_model=ApplyMenuScanResponse,
# )
# async def apply_menu_scan(
#     payload: ApplyMenuScanRequest,
#     db: DBSession,
#     restaurant: Restaurant = Depends(_scan),
#     _: User = Depends(_manager),
# ) -> ApplyMenuScanResponse:
#     """Write only the rows the owner approved (PRD §18: never auto-publish)."""
#     created, skipped = await MenuScanService(db).apply(restaurant.id, payload)
#     return ApplyMenuScanResponse(created=created, skipped=skipped)
