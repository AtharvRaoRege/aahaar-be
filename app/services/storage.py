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

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.supabase import get_supabase_client

LOGO_BUCKET = "venue-logos"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
LOGO_EDGE = 512
ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})


class StorageNotConfiguredError(RuntimeError):
    """Raised when the Supabase credentials the uploader needs are missing."""


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
    client = get_supabase_client()
    client.storage.from_(LOGO_BUCKET).upload(
        path,
        normalized,
        {"content-type": "image/png", "cache-control": "3600", "upsert": "true"},
    )
    public_url = client.storage.from_(LOGO_BUCKET).get_public_url(path)
    return f"{public_url.split('?')[0]}?v={uuid.uuid4().hex[:8]}"
