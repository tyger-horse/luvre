"""Plate pipeline: cover-crop to 4:5 at 1200×1500, palette of 3."""

from PIL import Image, ImageDraw

from app.services.plates import PLATE_HEIGHT, PLATE_WIDTH, compose_plate
from app.services.palette import extract_palette


def test_plate_is_4_5_and_filled():
    photo = Image.new("RGB", (600, 750), (120, 40, 30))
    plate = compose_plate(photo)
    assert plate.size == (PLATE_WIDTH, PLATE_HEIGHT)
    # Cover, not contain: every corner carries the photograph.
    for corner in [(0, 0), (1199, 0), (0, 1499), (1199, 1499)]:
        assert plate.getpixel(corner) == (120, 40, 30)


def test_wide_panorama_center_crops():
    photo = Image.new("RGB", (900, 300), (10, 10, 10))
    d = ImageDraw.Draw(photo)
    d.rectangle([400, 0, 500, 300], fill=(200, 30, 30))  # center stripe
    plate = compose_plate(photo)
    assert plate.size == (PLATE_WIDTH, PLATE_HEIGHT)
    assert plate.getpixel((600, 750)) == (200, 30, 30)


def test_tall_portrait_center_crops():
    photo = Image.new("RGB", (300, 900), (10, 10, 10))
    d = ImageDraw.Draw(photo)
    d.rectangle([0, 400, 300, 500], fill=(30, 200, 30))  # middle band
    plate = compose_plate(photo)
    assert plate.size == (PLATE_WIDTH, PLATE_HEIGHT)
    assert plate.getpixel((600, 750)) == (30, 200, 30)


def test_palette_has_three_entries():
    plate = compose_plate(Image.new("RGB", (800, 600), (90, 120, 80)))
    palette = extract_palette(plate)
    assert len(palette) == 3
    for color in palette:
        assert color.startswith("#") and len(color) == 7
