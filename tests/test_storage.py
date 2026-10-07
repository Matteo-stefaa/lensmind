from datetime import datetime
from pathlib import Path

from PIL import Image

from lensmind.camera.base import CapturedFile
from lensmind.camera.mock_image import render
from lensmind.storage import THUMB_SIZE, PhotoStore

JPEG = render(0.0, (900, 600))
WHEN = datetime(2026, 10, 7, 21, 1, 33)


def store_at(root: Path, *times: datetime) -> PhotoStore:
    moments = iter(times or (WHEN,) * 10)
    return PhotoStore(root, clock=lambda: next(moments))


def raw_plus_jpeg(number: int = 1) -> list[CapturedFile]:
    return [
        CapturedFile(f"DSC_{number:04d}.JPG", JPEG),
        CapturedFile(f"DSC_{number:04d}.NEF", b"raw"),
    ]


def test_save_prefixes_and_groups(tmp_path: Path) -> None:
    shot = store_at(tmp_path).save(raw_plus_jpeg())
    assert shot.id == "20261007-210133_DSC_0001"
    assert shot.files == ["20261007-210133_DSC_0001.JPG", "20261007-210133_DSC_0001.NEF"]
    assert shot.thumb == "20261007-210133_DSC_0001.JPG"
    assert (tmp_path / "20261007-210133_DSC_0001.NEF").read_bytes() == b"raw"


def test_thumbnail_is_a_small_jpeg(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    shot = store.save(raw_plus_jpeg())
    assert shot.thumb is not None
    thumb = store.thumb_path(shot.thumb)
    assert thumb is not None
    with Image.open(thumb) as image:
        assert max(image.size) <= THUMB_SIZE
    assert store.thumb_path(shot.files[1]) is None


def test_same_second_does_not_overwrite(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = store.save(raw_plus_jpeg(1))
    second = store.save(raw_plus_jpeg(1))
    assert first.id != second.id
    assert second.id == "20261007-210133-2_DSC_0001"
    assert len([p for p in tmp_path.iterdir() if p.is_file()]) == 4


def test_list_newest_first_with_limit(tmp_path: Path) -> None:
    store = store_at(
        tmp_path, datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11), datetime(2026, 1, 1, 12)
    )
    for number in (1, 2, 3):
        store.save(raw_plus_jpeg(number))
    shots = store.list_shots(limit=2)
    assert [shot.id for shot in shots] == [
        "20260101-120000_DSC_0003",
        "20260101-110000_DSC_0002",
    ]
    assert shots[0].thumb == "20260101-120000_DSC_0003.JPG"


def test_list_ignores_hidden_and_tolerates_foreign_files(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.save(raw_plus_jpeg())
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    (tmp_path / "notes.txt").write_text("hello")
    shots = store.list_shots()
    ids = {shot.id for shot in shots}
    assert ids == {"20261007-210133_DSC_0001", "notes"}
    assert next(shot for shot in shots if shot.id == "notes").thumb is None


def test_resolve_rejects_unsafe_or_missing_names(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    shot = store.save(raw_plus_jpeg())
    assert store.resolve(shot.files[0]) == tmp_path / shot.files[0]
    for name in ["../etc/passwd", "..", ".thumbs", "a/b", "a\\b", "missing.jpg", ""]:
        assert store.resolve(name) is None


def test_camera_folders_are_stripped_from_names(tmp_path: Path) -> None:
    shot = store_at(tmp_path).save([CapturedFile("/store/DCIM/../DSC_0009.JPG", JPEG)])
    assert shot.files == ["20261007-210133_DSC_0009.JPG"]
    assert (tmp_path / "20261007-210133_DSC_0009.JPG").is_file()
