"""Upload handling (§9 hardening, minus background removal).

The founders cut their own plates by hand, so the pipeline is: validate
→ persist the original → cover-crop the 4:5 plate → palette from the
hung plate. `bg_state` is `done` at upload; the column stays so a
future pipeline (or the review desk) has somewhere to live.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.services.palette import extract_palette
from app.services.plates import compose_plate

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_SLOTS = 4  # slot 0 = the hanging, 1–3 = detail views


def media_root() -> Path:
    root = Path(settings.MEDIA_DIR)
    for sub in ("originals", "plates"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _save_png(image: Image.Image, sub: str) -> str:
    """Persist as PNG, return the media-relative path. UUID names only."""
    rel = f"{sub}/{uuid.uuid4().hex}.png"
    image.save(media_root() / rel, format="PNG")
    return rel


def decode_upload(data: bytes) -> Image.Image:
    """Sniff the real image with Pillow (never trust the client), decode fully."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("That photograph is heavier than 25 MB.")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()  # decode fully — rejects polyglots and truncated files
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("That file would not open as a photograph.") from exc
    if image.format not in ("JPEG", "PNG", "WEBP", "TIFF", "BMP"):
        raise ValueError("Only JPEG, PNG, or WebP photographs may hang here.")
    return image.convert("RGB")


def store_upload(data: bytes) -> dict:
    """Validate + persist the original; cover-crop the hung plate."""
    image = decode_upload(data)
    plate = compose_plate(image)
    return {
        "original_path": _save_png(image, "originals"),
        "plate_path": _save_png(plate, "plates"),
        "palette": extract_palette(plate),
        "width": image.width,
        "height": image.height,
    }
