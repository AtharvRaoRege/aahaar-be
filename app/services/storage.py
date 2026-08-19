"""Uploads for owner-supplied images, backed by Supabase Storage.

Only logos for now. Two rules shape this module:

* Nothing the owner sends is stored verbatim. Every upload is decoded with Pillow,
  flattened, squared and re-encoded as PNG, which both normalises the display and
  discards anything that merely claims to be an image.
* The object path is derived from the restaurant id, so re-uploading replaces the
  previous logo instead of accumulating orphans.
"""

from __future__ import annotations

import uuid
from io import BytesIO

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import AppError, ValidationError
from app.core.logging import get_logger

logger = get_logger("aahaar.storage")

LOGO_BUCKET = "venue-logos"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
LOGO_EDGE = 512
ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


class StorageNotConfiguredError(RuntimeError):
    """Raised when the Supabase credentials the uploader needs are missing."""


class StorageUploadError(AppError):
    """Storage refused the upload. Carries a message the owner can act on."""

    status_code = 502
    code = "STORAGE_UPLOAD_FAILED"
    message = "Image storage could not accept the upload."


def storage_enabled() -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _square_png(payload: bytes) -> bytes:
    """Re-encode an upload as a square PNG, or reject it."""
    try:
        with Image.open(BytesIO(payload)) as source:
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError(
            "That file is not an image we can read.", code="INVALID_IMAGE"
        ) from exc

    edge = max(image.width, image.height)
    canvas = Image.new("RGBA", (edge, edge), (0, 0, 0, 0))
    canvas.paste(image, ((edge - image.width) // 2, (edge - image.height) // 2))
    if edge > LOGO_EDGE:
        canvas = canvas.resize((LOGO_EDGE, LOGO_EDGE), Image.LANCZOS)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def upload_venue_logo(restaurant_id: uuid.UUID, content_type: str, payload: bytes) -> str:
    """Store a venue logo and return its public URL."""
    if not storage_enabled():
        raise StorageNotConfiguredError()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValidationError("Keep the logo under 2 MB.", code="FILE_TOO_LARGE")
    if content_type and content_type.split(";")[0].strip() not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Upload a PNG, JPEG or WebP image.", code="UNSUPPORTED_IMAGE_TYPE")

    normalized = _square_png(payload)
    # Stable path per venue: a new logo overwrites the old one rather than leaking
    # objects nobody references. The query string is what busts browser caches.
    path = f"{restaurant_id}/logo.png"
    base = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key

    # Called over plain HTTP rather than through the supabase-py storage client on
    # purpose. That client's error handler reads `.text` off an already-parsed dict
    # (storage3 2.31 file_api._request), so any error whose body lacks one of
    # message/error/statusCode surfaces as an AttributeError and hides the real
    # cause — a wrong service-role key or a missing bucket looked identical to a
    # library crash.
    try:
        response = httpx.post(
            f"{base}/storage/v1/object/{LOGO_BUCKET}/{path}",
            content=normalized,
            headers={
                "Authorization": f"Bearer {key}",
                "apikey": key,
                "Content-Type": "image/png",
                "Cache-Control": "3600",
                "x-upsert": "true",
            },
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("Logo upload could not reach storage: %s", exc)
        raise StorageUploadError("Could not reach image storage.") from exc

    if response.status_code >= 400:
        # Log the real status and body; return something a person can act on.
        logger.warning(
            "Logo upload rejected by storage: %s %s", response.status_code, response.text[:400]
        )
        raise StorageUploadError(_upload_hint(response))

    return f"{base}/storage/v1/object/public/{LOGO_BUCKET}/{path}?v={uuid.uuid4().hex[:8]}"


def _upload_hint(response: httpx.Response) -> str:
    """Turn a storage rejection into something the owner can act on.

    Supabase answers with HTTP 400 and puts the code that actually matters in the
    body (``{"statusCode": "403", "error": "Unauthorized", ...}``), so the body is
    the more reliable signal.
    """
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        raw = str(body.get("statusCode") or "").strip()
        if raw.isdigit():
            status = int(raw)

    if status in (401, 403):
        return (
            "Image storage rejected our credentials. Check SUPABASE_SERVICE_ROLE_KEY "
            "belongs to the same project as SUPABASE_URL."
        )
    if status == 404:
        return (
            "The image storage bucket is missing. Apply the database migrations so the "
            f"'{LOGO_BUCKET}' bucket exists."
        )
    if status == 413:
        return "That image is too large for storage."
    return "Image storage could not accept the upload."
