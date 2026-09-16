"""4:5 plate composition — what the gallery hangs.

No background removal: the photograph is cover-cropped to the 4:5
frame (center-weighted) and resized to 1200×1500. What the founder
hangs is what the buyer sees.
"""

from __future__ import annotations

import math

from PIL import Image

PLATE_WIDTH = 1200
PLATE_HEIGHT = 1500


def compose_plate(photo: Image.Image) -> Image.Image:
    """Cover-crop `photo` to 4:5, centered, at 1200×1500."""
    rgb = photo.convert("RGB")
    scale = max(PLATE_WIDTH / rgb.width, PLATE_HEIGHT / rgb.height)
    grown = rgb.resize(
        (math.ceil(rgb.width * scale), math.ceil(rgb.height * scale)),
        Image.LANCZOS,
    )
    left = (grown.width - PLATE_WIDTH) // 2
    top = (grown.height - PLATE_HEIGHT) // 2
    return grown.crop((left, top, left + PLATE_WIDTH, top + PLATE_HEIGHT))
