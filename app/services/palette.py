"""Palette extraction — port of the demo's 4-bit bucket quantizer.

Operates on opaque pixels only; the transparent surround of a cutout
must never vote on the frame colours.
"""

from __future__ import annotations

from PIL import Image


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def opaque_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    rgba = image.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    out: list[tuple[int, int, int]] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 16:
                out.append((r, g, b))
    return out


def extract_palette(image: Image.Image, n: int = 3) -> list[str]:
    """Quantize to 4-bit buckets, keep the most frequent, min-distance pick of n."""
    pixels = opaque_pixels(image)
    if not pixels:
        return ["#2a2a2a"] * n
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for r, g, b in pixels:
        key = (r >> 4, g >> 4, b >> 4)
        cell = buckets.get(key)
        if cell is None:
            buckets[key] = [1, r, g, b]
        else:
            cell[0] += 1
            cell[1] += r
            cell[2] += g
            cell[3] += b
    ranked = sorted(buckets.values(), key=lambda c: c[0], reverse=True)
    means = [(c[1] // c[0], c[2] // c[0], c[3] // c[0]) for c in ranked]
    picked: list[tuple[int, int, int]] = []
    for m in means:
        if len(picked) >= n:
            break
        if all(_dist2(m, p) >= 40 * 40 for p in picked):
            picked.append(m)
    for m in means:
        if len(picked) >= n:
            break
        if m not in picked:
            picked.append(m)
    while len(picked) < n:
        picked.append(picked[-1])
    return [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in picked[:n]]


def opaque_coverage(image: Image.Image) -> float:
    """Fraction of pixels with meaningful alpha, in [0, 1]."""
    rgba = image.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    total = w * h
    if total == 0:
        return 0.0
    opaque = sum(1 for y in range(h) for x in range(w) if px[x, y][3] > 16)
    return opaque / total


def classify_bg_state(coverage: float) -> str:
    """Flag unusable removals for studio review (§9 QC: <3% or >97%)."""
    if coverage < 0.03 or coverage > 0.97:
        return "review"
    return "done"
