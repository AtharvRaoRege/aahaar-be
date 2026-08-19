"""Menu scanning with local OCR — no external service, no per-scan cost.

Tesseract reads the image on this server; the parser below turns its raw lines
into ``(section, dish, price)`` rows. Nothing leaves the machine and nothing is
metered.

The two hard rules from PRD §18 still hold, and are enforced here rather than
trusted to the UI:

* **Nothing is auto-published.** :meth:`MenuScanService.scan` only reads. Writing
  happens exclusively in :meth:`MenuScanService.apply`, from rows the owner
  approved.
* **Uncertainty is surfaced.** OCR on a phone photo is genuinely error-prone, so
  every row carries a confidence derived from Tesseract's own per-word scores and
  from how cleanly the line parsed.
"""

from __future__ import annotations

import io
import re
import shutil
import uuid
from decimal import Decimal, InvalidOperation

import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pytesseract import Output, TesseractNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ValidationError
from app.core.logging import get_logger
from app.schemas.menu_scan import ApplyMenuScanRequest, MenuScanResponse, MenuScanRow
from app.services.menu import MenuService
from app.services.menu_import import ImportRow, parse_csv, parse_xlsx

logger = get_logger("aahaar.menu_scan")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 300
MAX_PDF_PAGES = 12

# Tesseract reads small text badly. Upscale anything under this width first.
MIN_OCR_WIDTH = 1400
MAX_OCR_WIDTH = 3000

# Page segmentation modes worth trying: a uniform block, then a single column of
# mixed sizes. Menus land in one or the other depending on the layout.
PSM_MODES = (6, 4)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SHEET_SUFFIXES = {".csv", ".xlsx"}
SHEET_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Price at the end of a line: optional currency, digits, optional decimals, and
# the trailing "/-" that Indian menus use.
_PRICE = r"(?:₹|rs\.?|inr)?\s*(\d{1,5}(?:[.,]\d{1,2})?)\s*(?:/-|/=|\-)?"
PRICE_TAIL_RE = re.compile(rf"{_PRICE}(?:\s*[/|]\s*{_PRICE})?\s*$", re.IGNORECASE)

# A line that is nothing but a price: some PDF extractors put the dish name and
# its price on separate lines.
BARE_PRICE_RE = re.compile(rf"^{_PRICE}$", re.IGNORECASE)

# Dot/dash leaders between a dish and its price.
LEADER_RE = re.compile(r"[.·•\-_\s]{2,}$")

# Lines that are page furniture rather than menu content.
NOISE_RE = re.compile(
    r"^(?:menu|our menu|food menu|price list|gst|gstin|taxes?|tax extra|"
    r"all prices?|prices? (?:are )?(?:in|inclusive|exclusive).*|"
    r"veg(?:etarian)?|non[- ]?veg(?:etarian)?|"
    r"thank you.*|visit again.*|www\..*|https?://.*|"
    r"tel|ph|phone|mob|mobile|contact)\.?$",
    re.IGNORECASE,
)

# A heading that names a known menu section, whatever case it arrived in.
SECTION_WORDS = (
    "starter",
    "appetiser",
    "appetizer",
    "soup",
    "salad",
    "snack",
    "main",
    "entree",
    "curry",
    "gravy",
    "tandoor",
    "grill",
    "biryani",
    "rice",
    "noodle",
    "bread",
    "roti",
    "naan",
    "side",
    "accompaniment",
    "dessert",
    "sweet",
    "ice cream",
    "beverage",
    "drink",
    "juice",
    "shake",
    "coffee",
    "tea",
    "mocktail",
    "cocktail",
    "combo",
    "thali",
    "platter",
    "pizza",
    "burger",
    "sandwich",
    "roll",
    "wrap",
    "chinese",
    "continental",
    "south indian",
    "north indian",
    "breakfast",
    "lunch",
    "dinner",
    "special",
)

DEFAULT_SECTION = "Main Course"


class ScanUnavailableError(AppError):
    status_code = 503
    code = "SCAN_UNAVAILABLE"
    message = "Menu scanning is not available on this server yet."


class _Line:
    __slots__ = ("confidence", "text")

    def __init__(self, text: str, confidence: float) -> None:
        self.text = text
        self.confidence = confidence


class MenuScanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.menu = MenuService(session)

    # ── Read (never writes) ──────────────────────────────────
    async def scan(
        self, restaurant_id: uuid.UUID, filename: str, content_type: str, payload: bytes
    ) -> MenuScanResponse:
        if not payload:
            raise ValidationError("That file is empty.")
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ValidationError("Menu files must be 10 MB or smaller.")

        lowered = (filename or "").lower()
        media = content_type.split(";")[0].strip().lower()
        is_pdf = media == "application/pdf" or lowered.endswith(".pdf")
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

        if is_pdf:
            lines, quality, note = self._read_pdf(payload)
        else:
            lines, quality, note = self._read_image(lowered, payload)

        rows = parse_menu_lines(lines)
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

    # ── Apply (the only path that writes) ────────────────────
    async def apply(
        self, restaurant_id: uuid.UUID, payload: ApplyMenuScanRequest
    ) -> tuple[int, int]:
        rows: list[ImportRow] = []
        for row in payload.rows:
            name = row.name.strip()
            if not name or row.price is None or row.price <= 0:
                # Refuse to write a dish the owner has not given a real price.
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

    # ── Input handling ───────────────────────────────────────
    def _read_image(self, lowered: str, payload: bytes) -> tuple[list[_Line], str, str | None]:
        if lowered and not any(lowered.endswith(suffix) for suffix in IMAGE_SUFFIXES):
            raise ValidationError("Upload a photo (JPG, PNG), a PDF, a CSV, or an Excel file.")
        try:
            image = Image.open(io.BytesIO(payload))
            image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError("That file is not a readable image.") from exc

        prepared = self._prepare(image)
        best: list[_Line] = []
        best_score = -1.0
        for psm in PSM_MODES:
            lines = self._ocr(prepared, psm)
            # Score a pass by how many priced dish lines it actually produced.
            score = float(sum(1 for line in lines if PRICE_TAIL_RE.search(line.text)))
            if score > best_score:
                best, best_score = lines, score

        mean_confidence = sum(line.confidence for line in best) / len(best) if best else 0.0
        quality = "GOOD" if mean_confidence >= 70 and best_score > 0 else "POOR"
        note = None
        if quality == "POOR":
            note = (
                "This photo was hard to read, so check every row. A straight, bright "
                "shot of one page — no shadows, no angle — reads much better."
            )
        return best, quality, note

    def _read_pdf(self, payload: bytes) -> tuple[list[_Line], str, str | None]:
        try:
            reader = PdfReader(io.BytesIO(payload))
        except Exception as exc:
            raise ValidationError("That PDF could not be opened.") from exc

        collected: list[_Line] = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = ""
            try:
                text = page.extract_text(extraction_mode="layout") or ""
            except Exception:
                logger.debug("Layout extraction unavailable; falling back")
            if not text.strip():
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
            for raw in text.splitlines():
                cleaned = " ".join(raw.split())
                if cleaned:
                    # Embedded PDF text is exact — no OCR uncertainty to model.
                    collected.append(_Line(cleaned, 100.0))

        if not collected:
            return (
                [],
                "POOR",
                "This PDF has no selectable text — it is a scan. Upload a photo of the "
                "menu instead and we will read that.",
            )
        note = "Only the first 12 pages were read." if len(reader.pages) > MAX_PDF_PAGES else None
        return collected, "GOOD", note

    def _read_sheet(
        self, lowered: str, payload: bytes
    ) -> tuple[list[MenuScanRow], str, str | None]:
        imported = parse_csv(payload) if lowered.endswith(".csv") else parse_xlsx(payload)
        rows = [
            MenuScanRow(
                name=row.name,
                category=row.category,
                price=row.price,
                description=row.description,
                is_vegetarian=row.is_vegetarian,
                confidence="HIGH",
            )
            for row in imported
        ]
        if not rows:
            return (
                [],
                "POOR",
                "No dishes found. Use columns Dish name, Category, and Price (INR).",
            )
        return rows, "GOOD", None

    def _prepare(self, image: Image.Image) -> Image.Image:
        """Grayscale, deskew-free upscale, and autocontrast — cheap OCR wins."""
        prepared = ImageOps.exif_transpose(image).convert("L")
        width, height = prepared.size
        if width < MIN_OCR_WIDTH:
            scale = MIN_OCR_WIDTH / float(width)
            prepared = prepared.resize((MIN_OCR_WIDTH, max(1, int(height * scale))), Image.LANCZOS)
        elif width > MAX_OCR_WIDTH:
            scale = MAX_OCR_WIDTH / float(width)
            prepared = prepared.resize((MAX_OCR_WIDTH, max(1, int(height * scale))), Image.LANCZOS)
        return ImageOps.autocontrast(prepared)

    def _ocr(self, image: Image.Image, psm: int) -> list[_Line]:
        if shutil.which("tesseract") is None:
            raise ScanUnavailableError(
                "Menu scanning needs the tesseract package installed on the server."
            )
        try:
            data = pytesseract.image_to_data(
                image,
                config=f"--oem 3 --psm {psm}",
                output_type=Output.DICT,
            )
        except TesseractNotFoundError as exc:
            raise ScanUnavailableError(
                "Menu scanning needs the tesseract package installed on the server."
            ) from exc
        except Exception as exc:
            logger.exception("OCR failed")
            raise ValidationError(
                "Could not read that image. Try a clearer photo.",
                code="SCAN_FAILED",
            ) from exc

        return _group_words_into_lines(data)


def _group_words_into_lines(data: dict) -> list[_Line]:
    """Rebuild text lines from Tesseract's word boxes, keeping confidence."""
    buckets: dict[tuple[int, int, int, int], list[tuple[int, str, float]]] = {}
    for index, word in enumerate(data.get("text", [])):
        text = (word or "").strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][index])
        except (KeyError, IndexError, TypeError, ValueError):
            confidence = 0.0
        if confidence < 0:
            continue
        key = (
            data["page_num"][index],
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index],
        )
        buckets.setdefault(key, []).append((data["left"][index], text, confidence))

    lines: list[_Line] = []
    for key in sorted(buckets):
        words = sorted(buckets[key], key=lambda item: item[0])
        text = " ".join(word for _, word, _ in words)
        confidence = sum(score for _, _, score in words) / len(words)
        lines.append(_Line(text, confidence))
    return lines


# ── Line parsing ─────────────────────────────────────────────
def _looks_like_section(text: str) -> bool:
    stripped = text.strip(" :-–—*|")  # noqa: RUF001
    if not stripped or any(ch.isdigit() for ch in stripped):
        return False
    words = stripped.split()
    if len(words) > 5:
        return False
    lowered = stripped.lower()
    if any(word in lowered for word in SECTION_WORDS):
        return True
    letters = [ch for ch in stripped if ch.isalpha()]
    if len(letters) < 3:
        return False
    # A short all-caps line with no price is almost always a section heading.
    return all(ch.isupper() for ch in letters)


def _title_case_section(text: str) -> str:
    cleaned = " ".join(text.strip(" :-–—*|").split())  # noqa: RUF001
    if cleaned.isupper() or cleaned.islower():
        return cleaned.title()[:120]
    return cleaned[:120]


def _to_decimal(raw: str) -> Decimal | None:
    candidate = raw.replace(",", ".").strip()
    try:
        value = Decimal(candidate).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    # A four-figure-plus "price" on a menu line is nearly always a misread.
    return value if Decimal("1") <= value <= Decimal("99999") else None


def _money(value: Decimal) -> str:
    """Drop the trailing ``.00`` so the note reads like a menu, not a ledger."""
    quantized = value.normalize()
    return f"{quantized:f}"


def _clean_name(text: str) -> str:
    name = LEADER_RE.sub("", text)
    name = name.strip(" .·•-_–—:|")  # noqa: RUF001
    name = re.sub(r"\s{2,}", " ", name)
    # Strip a leading menu index like "12." or "3)".
    name = re.sub(r"^\d{1,3}\s*[.)]\s*", "", name)
    return name.strip()


def _plausible_name(name: str) -> bool:
    letters = [ch for ch in name if ch.isalpha()]
    return len(letters) >= 3 and len(name) <= 160


def parse_menu_lines(lines: list[_Line]) -> list[MenuScanRow]:
    """Turn OCR/PDF text lines into reviewable dish rows.

    Pure and dependency-free so it can be exercised without an image.
    """
    rows: list[MenuScanRow] = []
    section = DEFAULT_SECTION
    seen: set[str] = set()
    # Holds a dish name that arrived without a price, in case the next line is
    # the bare price belonging to it.
    pending_name: str | None = None

    for line in lines:
        text = " ".join(line.text.split())
        if not text or NOISE_RE.match(text.strip(" .:-")):
            continue

        bare = BARE_PRICE_RE.match(text)
        if bare is not None and pending_name is not None:
            price = _to_decimal(bare.group(1))
            name = pending_name
            pending_name = None
            if price is None or not _plausible_name(name):
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                MenuScanRow(
                    name=name[:160],
                    category=section,
                    price=price,
                    description=None,
                    is_vegetarian=None,
                    confidence=_confidence_for(line.confidence, name, 1),
                )
            )
            continue

        match = PRICE_TAIL_RE.search(text)
        if match is None:
            pending_name = None
            if _looks_like_section(text):
                section = _title_case_section(text)
            elif rows and len(text) > 12 and not text.isupper():
                # An unpriced sentence right after a dish reads as its description.
                previous = rows[-1]
                if previous.description is None:
                    previous.description = text[:1000]
            elif _plausible_name(_clean_name(text)):
                # Might be a dish whose price is on the next line.
                pending_name = _clean_name(text)
            continue

        pending_name = None

        name = _clean_name(text[: match.start()])
        if not _plausible_name(name):
            # A price with no dish attached: most likely a stray column heading.
            continue

        primary = _to_decimal(match.group(1))
        secondary = _to_decimal(match.group(2)) if match.group(2) else None
        prices = [value for value in (primary, secondary) if value is not None]
        if not prices:
            continue
        price = min(prices)

        description: str | None = None
        if len(prices) > 1:
            description = f"Also available at ₹{_money(max(prices))}"

        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)

        rows.append(
            MenuScanRow(
                name=name[:160],
                category=section,
                price=price,
                description=description,
                is_vegetarian=None,
                confidence=_confidence_for(line.confidence, name, len(prices)),
            )
        )

    return rows


def _confidence_for(ocr_confidence: float, name: str, price_count: int) -> str:
    """How much the owner should trust this row.

    Deliberately pessimistic: a wrong price on a live menu costs the restaurant
    money, so anything short of a clean read is flagged for human eyes.
    """
    if ocr_confidence < 60 or price_count > 1:
        return "LOW"
    words = len(name.split())
    if ocr_confidence >= 85 and words >= 2:
        return "HIGH"
    if ocr_confidence >= 75 and words >= 1:
        return "MEDIUM"
    return "LOW"
