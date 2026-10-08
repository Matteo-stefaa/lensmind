"""Saving downloaded shots on the Pi, listing them and serving them safely."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from lensmind.camera.base import CapturedFile

THUMB_SIZE = 400
THUMB_DIR = ".thumbs"
IMAGE_SUFFIXES = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class Shot:
    id: str
    files: list[str]
    thumb: str | None


class PhotoStore:
    def __init__(self, root: Path, clock: Callable[[], datetime] = datetime.now) -> None:
        self.root = root
        self._thumbs = root / THUMB_DIR
        self._thumbs.mkdir(parents=True, exist_ok=True)
        self._clock = clock

    def save(self, files: list[CapturedFile]) -> Shot:
        base_names = [_safe_name(f.name) for f in files]
        prefix = self._free_prefix(base_names)
        names = []
        for captured, base_name in zip(files, base_names, strict=True):
            name = f"{prefix}_{base_name}"
            (self.root / name).write_bytes(captured.data)
            if Path(name).suffix.lower() in IMAGE_SUFFIXES:
                self._make_thumb(name)
            names.append(name)
        return self._shot(Path(names[0]).stem, names)

    def list_shots(self, limit: int = 50) -> list[Shot]:
        groups: dict[str, list[Path]] = {}
        for path in self.root.iterdir():
            if path.name.startswith(".") or not path.is_file():
                continue
            groups.setdefault(path.stem, []).append(path)

        def newest(item: tuple[str, list[Path]]) -> tuple[int, str]:
            stem, paths = item
            return max(p.stat().st_mtime_ns for p in paths), stem

        ordered = sorted(groups.items(), key=newest, reverse=True)[:limit]
        return [self._shot(stem, sorted(p.name for p in paths)) for stem, paths in ordered]

    def resolve(self, name: str) -> Path | None:
        if not _is_plain_name(name):
            return None
        path = self.root / name
        return path if path.is_file() else None

    def thumb_path(self, name: str) -> Path | None:
        if self.resolve(name) is None:
            return None
        path = self._thumbs / f"{name}.jpg"
        return path if path.is_file() else None

    def _free_prefix(self, base_names: list[str]) -> str:
        stamp = self._clock().strftime("%Y%m%d-%H%M%S")
        prefix, attempt = stamp, 1
        while any((self.root / f"{prefix}_{name}").exists() for name in base_names):
            attempt += 1
            prefix = f"{stamp}-{attempt}"
        return prefix

    def _shot(self, stem: str, names: list[str]) -> Shot:
        thumb = next((n for n in names if (self._thumbs / f"{n}.jpg").is_file()), None)
        return Shot(id=stem, files=names, thumb=thumb)

    def _make_thumb(self, name: str) -> None:
        try:
            with Image.open(self.root / name) as image:
                image.draft("RGB", (THUMB_SIZE, THUMB_SIZE))
                thumb = image.convert("RGB")
                thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
                thumb.save(self._thumbs / f"{name}.jpg", "JPEG", quality=80)
        except (OSError, Image.DecompressionBombError):
            pass  # the original is kept; the gallery shows it without a thumbnail


def _safe_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1].lstrip(".")
    return base or "file"


def _is_plain_name(name: str) -> bool:
    return bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name
