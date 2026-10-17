"""A test shot as the model sees it: a small JPEG, histogram stats and shooting data.

Full-resolution files never leave the Pi: only the downscaled copy is sent.
"""

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageOps

LONG_EDGE = 1024
JPEG_QUALITY = 80
# Luminance at or above / at or below these counts as clipped.
CLIP_HIGH = 250
CLIP_LOW = 5
# A channel at 255 has lost detail even when luminance has not (e.g. a red sunset).
CHANNEL_CLIP = 255
HISTOGRAM_BINS = 8
JPEG_SUFFIXES = (".jpg", ".jpeg")

EXIF_IFD = 0x8769
# EXIF tag ids: Pillow names them only in ExifTags.TAGS, ids are stable.
EXPOSURE_TIME = 0x829A
F_NUMBER = 0x829D
EXPOSURE_PROGRAM = 0x8822
ISO = 0x8827
EXPOSURE_BIAS = 0x9204
METERING_MODE = 0x9207
FLASH = 0x9209
FOCAL_LENGTH = 0x920A
WHITE_BALANCE = 0xA403
FOCAL_LENGTH_35MM = 0xA405

EXPOSURE_PROGRAMS = {
    1: "manual",
    2: "program",
    3: "aperture priority",
    4: "shutter priority",
    5: "creative",
    6: "action",
    7: "portrait",
    8: "landscape",
}
METERING_MODES = {
    1: "average",
    2: "center-weighted",
    3: "spot",
    4: "multi-spot",
    5: "matrix",
    6: "partial",
}


class StoredShot(Protocol):
    @property
    def files(self) -> list[str]: ...


class PhotoSource(Protocol):
    """Where test shots are read from: the photo store, by structure."""

    def list_shots(self, limit: int = ...) -> Sequence[StoredShot]: ...

    def resolve(self, name: str) -> Path | None: ...


@dataclass(frozen=True)
class LatestShot:
    files: list[str]
    taken_at: float  # POSIX time of the newest file
    jpeg_name: str | None
    jpeg: bytes | None


@dataclass(frozen=True)
class ShotView:
    jpeg: bytes
    width: int
    height: int
    stats: dict[str, Any]
    shooting: dict[str, Any]


def latest_shot(photos: PhotoSource) -> LatestShot | None:
    shots = photos.list_shots(1)
    if not shots:
        return None
    paths = [path for name in shots[0].files if (path := photos.resolve(name)) is not None]
    if not paths:
        return None
    jpeg = next((p for p in paths if p.suffix.lower() in JPEG_SUFFIXES), None)
    return LatestShot(
        files=[path.name for path in paths],
        taken_at=max(path.stat().st_mtime for path in paths),
        jpeg_name=jpeg.name if jpeg else None,
        jpeg=jpeg.read_bytes() if jpeg else None,
    )


def view_shot(data: bytes) -> ShotView:
    """Downscale a JPEG and measure it. Raises OSError if it cannot be decoded."""
    try:
        return _view_shot(data)
    except Image.DecompressionBombError as error:
        raise OSError(str(error)) from error


def _view_shot(data: bytes) -> ShotView:
    with Image.open(io.BytesIO(data)) as original:
        # draft() lets the decoder skip most of a 24 MP file: fast and small on a Pi Zero.
        original.draft("RGB", (LONG_EDGE, LONG_EDGE))
        shooting = shooting_data(original.getexif())
        image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((LONG_EDGE, LONG_EDGE))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return ShotView(buffer.getvalue(), image.width, image.height, histogram_stats(image), shooting)


def histogram_stats(image: Image.Image) -> dict[str, Any]:
    """Exposure numbers the model can trust more than its own reading of the picture."""
    luma = image.convert("L").histogram()
    total = sum(luma)

    def percent(count: float) -> float:
        return round(100 * count / total, 1)

    cumulative, median = 0, 0
    for level, count in enumerate(luma):
        cumulative += count
        if cumulative * 2 >= total:
            median = level
            break
    channels = image.histogram()
    width = 256 // HISTOGRAM_BINS
    return {
        "mean_luminance": round(sum(level * n for level, n in enumerate(luma)) / total, 1),
        "median_luminance": median,
        "clipped_highlights_percent": percent(sum(luma[CLIP_HIGH:])),
        "clipped_shadows_percent": percent(sum(luma[: CLIP_LOW + 1])),
        "channel_clipped_percent": {
            name: percent(channels[offset + CHANNEL_CLIP])
            for name, offset in (("red", 0), ("green", 256), ("blue", 512))
        },
        "channel_mean": {
            name: round(sum(level * n for level, n in enumerate(channels[o : o + 256])) / total, 1)
            for name, o in (("red", 0), ("green", 256), ("blue", 512))
        },
        "luminance_histogram_percent": [
            percent(sum(luma[start : start + width])) for start in range(0, 256, width)
        ],
    }


def shooting_data(exif: Image.Exif) -> dict[str, Any]:
    """Exposure parameters recorded by the camera in the file, where present."""
    tags = {**exif, **exif.get_ifd(EXIF_IFD)}
    data: dict[str, Any] = {}
    if (value := _number(tags.get(EXPOSURE_TIME))) is not None and value > 0:
        data["exposure_time"] = _seconds(value)
    if (value := _number(tags.get(F_NUMBER))) is not None and value > 0:
        data["f_number"] = f"f/{value:g}"
    if (value := _number(tags.get(ISO))) is not None:
        data["iso"] = int(value)
    if (value := _number(tags.get(EXPOSURE_BIAS))) is not None:
        data["exposure_compensation_ev"] = round(value, 2)
    if (value := _number(tags.get(FOCAL_LENGTH))) is not None and value > 0:
        data["focal_length_mm"] = round(value, 1)
    if (value := _number(tags.get(FOCAL_LENGTH_35MM))) is not None and value > 0:
        data["focal_length_35mm"] = int(value)
    if (value := _number(tags.get(EXPOSURE_PROGRAM))) in EXPOSURE_PROGRAMS:
        data["exposure_program"] = EXPOSURE_PROGRAMS[int(value)]
    if (value := _number(tags.get(METERING_MODE))) in METERING_MODES:
        data["metering"] = METERING_MODES[int(value)]
    if (value := _number(tags.get(WHITE_BALANCE))) is not None:
        data["white_balance"] = "manual" if value else "auto"
    if (value := _number(tags.get(FLASH))) is not None:
        data["flash_fired"] = bool(int(value) & 1)
    return data


def _number(value: object) -> float | None:
    if isinstance(value, tuple):  # some writers store a single value as a 1-tuple
        value = value[0] if value else None
    try:
        number = float(value)  # type: ignore[arg-type]  # IFDRational, int, float
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return number if math.isfinite(number) else None


def _seconds(value: float) -> str:
    if value >= 0.3:
        return f"{value:g} s"
    return f"1/{round(1 / value)} s"
