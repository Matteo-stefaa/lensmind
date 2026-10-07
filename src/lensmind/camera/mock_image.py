"""Deterministic synthetic scene whose brightness follows the exposure error."""

import io
from functools import lru_cache

from PIL import Image, ImageDraw

PREVIEW_SIZE = (640, 426)
CAPTURE_SIZE = (1500, 1000)
GAMMA = 2.2


@lru_cache(maxsize=4)
def _scene(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    horizon = int(height * 0.62)
    for y in range(horizon):
        k = y / horizon
        sky = (int(120 + 60 * k), int(160 + 50 * k), int(215 + 20 * k))
        draw.line([(0, y), (width, y)], fill=sky)
    draw.rectangle([0, horizon, width, height], fill=(70, 95, 55))
    # Sun: the first area to clip when overexposed.
    radius, cx, cy = int(height * 0.08), int(width * 0.8), int(height * 0.18)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(250, 248, 235))
    # Deep shadow: the first area to block up when underexposed.
    shadow = [int(width * 0.05), int(height * 0.45), int(width * 0.25), height]
    draw.rectangle(shadow, fill=(18, 18, 22))
    # Subject.
    sx, sy, sr = int(width * 0.5), int(height * 0.55), int(height * 0.2)
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(190, 145, 120))
    return image


def render(error_stops: float, size: tuple[int, int]) -> bytes:
    """Return the scene as JPEG, exposed `error_stops` above (or below) correct."""
    factor = 2 ** (max(-10.0, min(10.0, error_stops)) / GAMMA)
    table = [min(255, round(value * factor)) for value in range(256)] * 3
    buffer = io.BytesIO()
    _scene(size).point(table).save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
