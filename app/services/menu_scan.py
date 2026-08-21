"""AI menu scan via Gemini — upload is read in memory and never stored.

CSV/XLSX still parse locally. Photos and PDFs go to Gemini when
``GEMINI_API_KEY`` is set. Apply writes only owner-approved rows.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory
from app.core.errors import AppError, NotFoundError, ServiceUnavailableError, ValidationError
from app.core.logging import get_logger
from app.schemas.menu_scan import (
    ApplyMenuScanRequest,
    MenuScanJobResponse,
    MenuScanResponse,
    MenuScanRow,
)
from app.services.menu import MenuService
from app.services.menu_import import ImportRow, parse_csv, parse_xlsx

logger = get_logger("aahaar.menu_scan")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 300
DEFAULT_SECTION = "Mains"
GEMINI_MODEL = "gemini-2.5-flash-lite"

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

# Compact prompt — keep keys stable for _map_gemini.
SCAN_PROMPT = r"""Extract menu dishes as valid raw JSON (no Markdown/backticks).

JSON Schema:
{"imageQuality":"GOOD"|"POOR","notes":string|null,"rows":[{"name":string,"category":string,"price":number|null,"description":string|null,"isVegetarian":boolean|null,"confidence":"HIGH"|"MEDIUM"|"LOW"}]}

Rules:
1. One dish/drink per row. Maintain order. Max 300 rows.
2. Category = section header. Skip headers/GST/contact/noise.
3. Price = plain number only (strip ₹/$/Rs/,). Use full price if half/full listed.
4. isVegetarian = true/false/null.
5. Set imageQuality="POOR" if unreadable. Add notes only if helpful."""

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
                "AI menu scan needs GEMINI_API_KEY on the server. Add it to .env and restart the API.",
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
            logger.exception("Gemini menu scan failed (model=%s)", GEMINI_MODEL)
            detail = str(exc).strip()
            hint = "Could not read that menu right now. Try again in a moment."
            lowered = detail.lower()
            if "api key" in lowered or "permission" in lowered or "401" in lowered:
                hint = "Gemini rejected the API key. Check GEMINI_API_KEY and restart the API."
            elif "not found" in lowered or "404" in lowered or "not supported" in lowered:
                hint = "Gemini could not use the configured model. Try again later."
            raise ServiceUnavailableError(hint, code="MENU_SCAN_FAILED") from exc

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


# ── Background jobs (same shape as Excel import) ─────────────
ScanStatus = Literal["pending", "running", "done", "failed"]
JOB_TTL_SECONDS = 2 * 60 * 60


@dataclass
class ScanJob:
    id: uuid.UUID
    restaurant_id: uuid.UUID
    status: ScanStatus = "pending"
    error: str | None = None
    result: MenuScanResponse | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_response(self) -> MenuScanJobResponse:
        return MenuScanJobResponse(
            job_id=self.id,
            status=self.status,
            error=self.error,
            result=self.result if self.status == "done" else None,
        )


_jobs: dict[uuid.UUID, ScanJob] = {}
_jobs_lock = asyncio.Lock()
_tasks: set[asyncio.Task[None]] = set()


async def start_scan(
    restaurant_id: uuid.UUID,
    filename: str,
    content_type: str,
    payload: bytes,
) -> ScanJob:
    if not payload:
        raise ValidationError("That file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValidationError("Menu files must be 10 MB or smaller.")

    job = ScanJob(id=uuid.uuid4(), restaurant_id=restaurant_id)
    async with _jobs_lock:
        _prune_jobs_locked()
        _jobs[job.id] = job

    task = asyncio.create_task(
        _run_scan(job.id, restaurant_id, filename, content_type, payload)
    )
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job


async def get_scan_job(job_id: uuid.UUID, restaurant_id: uuid.UUID) -> ScanJob:
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job.restaurant_id != restaurant_id:
        raise NotFoundError("Scan job not found.")
    return job


def _prune_jobs_locked() -> None:
    now = datetime.now(UTC)
    stale = [
        job_id
        for job_id, job in _jobs.items()
        if (now - job.started_at).total_seconds() > JOB_TTL_SECONDS
    ]
    for job_id in stale:
        _jobs.pop(job_id, None)


async def _run_scan(
    job_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    filename: str,
    content_type: str,
    payload: bytes,
) -> None:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "running"

    try:
        async with SessionFactory() as session:
            result = await MenuScanService(session).scan(
                restaurant_id, filename, content_type, payload
            )
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job.result = result
            job.status = "done"
    except (ValidationError, ServiceUnavailableError, AppError) as exc:
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = exc.message
    except Exception:
        logger.exception("Menu scan failed for restaurant %s job %s", restaurant_id, job_id)
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return
            job.status = "failed"
            job.error = "Could not read that menu right now. Try again in a moment."
