"""AI menu scan via Gemini — upload is read in memory and never stored.

CSV/XLSX still parse locally. Photos and PDFs go to Gemini when
``GEMINI_API_KEY`` is set. Apply writes only owner-approved rows.
"""

from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.schemas.menu_scan import ApplyMenuScanRequest, MenuScanResponse, MenuScanRow
from app.services.menu import MenuService
from app.services.menu_import import ImportRow, parse_csv, parse_xlsx

logger = get_logger("aahaar.menu_scan")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 300
DEFAULT_SECTION = "Mains"
GEMINI_MODEL = "gemini-2.0-flash"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SHEET_SUFFIXES = {".csv", ".xlsx"}
SHEET_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
}

SCAN_PROMPT = """You extract dishes from a restaurant menu (photo or PDF).

Return ONLY valid JSON matching this schema (no markdown, no commentary):
{
  "imageQuality": "GOOD" | "POOR",
  "notes": string | null,
  "rows": [
    {
      "name": string,
      "category": string,
      "price": number | null,
      "description": string | null,
      "isVegetarian": boolean | null,
      "confidence": "HIGH" | "MEDIUM" | "LOW"
    }
  ]
}

Rules:
- Each row is one sellable dish/drink with its section heading as category.
- Prefer Indian menu sections when clear (Starters, Mains, Breads, Beverages, Desserts, etc.).
- Prices are numbers only (INR). Strip ₹, Rs, /- and commas. Use the full plate price when half/full both appear.
- Skip headers, GST lines, phone numbers, addresses, "thank you", and empty decorative lines.
- isVegetarian: true for veg, false for non-veg, null if unknown. Do not invent.
- confidence HIGH if name+price clear; MEDIUM if one is fuzzy; LOW if guessed.
- imageQuality POOR if blurry, skewed, dark, or cut off.
- notes: short owner tip only when helpful; else null.
- Max 300 rows. Preserve reading order.
"""


class MenuScanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.menu = MenuService(session)

    async def scan(
        self, restaurant_id: uuid.UUID, filename: str, content_type: str, payload: bytes
    ) -> MenuScanResponse:
        _ = restaurant_id
        if not payload:
            raise ValidationError("That file is empty.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValidationError("Menu files must be 10 MB or smaller.")

        lowered = (filename or "").lower()
        media = content_type.split(";")[0].strip().lower()
        is_sheet = lowered.endswith(tuple(SHEET_SUFFIXES)) or media in SHEET_TYPES

        if is_sheet:
            rows, quality, note = self._read_sheet(lowered, payload)
            truncated = len(rows) > MAX_ROWS
            rows = rows[:MAX_ROWS]
            return MenuScanResponse(
                rows=rows,
                image_quality=quality,
                notes=note,
                low_confidence_count=sum(1 for row in rows if row.confidence == "LOW"),
                truncated=truncated,
            )

        if not settings.gemini_enabled:
            raise ServiceUnavailableError(
                "AI menu scan is not configured.",
                code="MENU_SCAN_DISABLED",
            )

        mime = self._resolve_mime(lowered, media)
        raw = await self._gemini_extract(payload, mime)
        return self._map_gemini(raw)

    async def apply(
        self, restaurant_id: uuid.UUID, payload: ApplyMenuScanRequest
    ) -> tuple[int, int]:
        rows: list[ImportRow] = []
        for row in payload.rows:
            name = row.name.strip()
            if not name or row.price is None or row.price <= 0:
                continue
            rows.append(
                ImportRow(
                    name=name,
                    category=(row.category.strip() or DEFAULT_SECTION),
                    price=row.price,
                    description=(row.description or "").strip() or None,
                    is_vegetarian=True if row.is_vegetarian is None else row.is_vegetarian,
                )
            )
        if not rows:
            raise ValidationError("Nothing to add. Give each dish a name and a price.")
        return await self.menu.import_dishes(restaurant_id, rows)

    def _read_sheet(self, lowered: str, payload: bytes) -> tuple[list[MenuScanRow], str, str | None]:
        if lowered.endswith(".csv"):
            imported = parse_csv(payload)
        elif lowered.endswith(".xlsx"):
            imported = parse_xlsx(payload)
        else:
            raise ValidationError("Upload a CSV or Excel (.xlsx) spreadsheet.")

        rows = [
            MenuScanRow(
                name=row.name,
                category=row.category or DEFAULT_SECTION,
                price=row.price,
                description=row.description,
                is_vegetarian=row.is_vegetarian,
                confidence="HIGH",
            )
            for row in imported
        ]
        note = None if rows else "No dishes found in that spreadsheet."
        return rows, "GOOD", note

    def _resolve_mime(self, lowered: str, media: str) -> str:
        if media.startswith("image/") or media == "application/pdf":
            return media
        for suffix, mime in MIME_BY_SUFFIX.items():
            if lowered.endswith(suffix):
                return mime
        raise ValidationError("Upload a photo (JPG, PNG, WebP), a PDF, a CSV, or an Excel file.")

    async def _gemini_extract(self, payload: bytes, mime: str) -> dict[str, Any]:
        client = genai.Client(api_key=settings.gemini_api_key.strip())
        try:
            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=payload, mime_type=mime),
                            types.Part.from_text(text=SCAN_PROMPT),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
        except Exception as exc:
            logger.exception("Gemini menu scan failed")
            raise ServiceUnavailableError(
                "Could not read that menu right now. Try again in a moment.",
                code="MENU_SCAN_FAILED",
            ) from exc

        text = (response.text or "").strip()
        if not text:
            raise ValidationError("No dishes could be read from that file.")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                raise ValidationError("No dishes could be read from that file.") from None
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValidationError("No dishes could be read from that file.")
        return parsed

    def _map_gemini(self, raw: dict[str, Any]) -> MenuScanResponse:
        quality_raw = str(raw.get("imageQuality") or raw.get("image_quality") or "GOOD").upper()
        quality = "POOR" if quality_raw == "POOR" else "GOOD"
        notes = raw.get("notes")
        note = str(notes).strip() if isinstance(notes, str) and notes.strip() else None

        rows: list[MenuScanRow] = []
        for item in raw.get("rows") or []:
            if not isinstance(item, dict):
                continue
            mapped = self._map_row(item)
            if mapped is not None:
                rows.append(mapped)

        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        if not rows and note is None:
            note = (
                "No dishes could be read. Try a straight, well-lit photo of one page "
                "at a time, filling the frame."
            )
        return MenuScanResponse(
            rows=rows,
            image_quality=quality,
            notes=note,
            low_confidence_count=sum(1 for row in rows if row.confidence == "LOW"),
            truncated=truncated,
        )

    def _map_row(self, item: dict[str, Any]) -> MenuScanRow | None:
        name = str(item.get("name") or "").strip()
        if not name:
            return None
        category = str(item.get("category") or DEFAULT_SECTION).strip() or DEFAULT_SECTION
        price = self._money(item.get("price"))
        description_raw = item.get("description")
        description = (
            str(description_raw).strip()[:1000]
            if isinstance(description_raw, str) and description_raw.strip()
            else None
        )
        veg = item.get("isVegetarian", item.get("is_vegetarian"))
        is_vegetarian = veg if isinstance(veg, bool) else None
        confidence_raw = str(item.get("confidence") or "MEDIUM").upper()
        confidence = confidence_raw if confidence_raw in {"HIGH", "MEDIUM", "LOW"} else "MEDIUM"
        return MenuScanRow(
            name=name[:160],
            category=category[:120],
            price=price,
            description=description,
            is_vegetarian=is_vegetarian,
            confidence=confidence,  # type: ignore[arg-type]
        )

    def _money(self, value: object) -> Decimal | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float, Decimal)):
            amount = Decimal(str(value))
        else:
            cleaned = re.sub(r"[^\d.,]", "", str(value)).replace(",", "")
            if not cleaned:
                return None
            try:
                amount = Decimal(cleaned)
            except InvalidOperation:
                return None
        if amount <= 0:
            return None
        return amount.quantize(Decimal("0.01"))
