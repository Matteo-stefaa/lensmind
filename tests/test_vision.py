import io
import os
from pathlib import Path

import pytest
from PIL import Image

from lensmind.assistant.vision import LONG_EDGE, histogram_stats, latest_shot, view_shot
from lensmind.camera.base import CapturedFile
from lensmind.camera.mock import MockCamera
from lensmind.storage import PhotoStore


def jpeg(image: Image.Image, **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", **options)
    return buffer.getvalue()


def test_downscales_to_the_long_edge() -> None:
    view = view_shot(jpeg(Image.new("RGB", (3000, 2000), (120, 120, 120))))
    assert (view.width, view.height) == (LONG_EDGE, 683)
    with Image.open(io.BytesIO(view.jpeg)) as small:
        assert small.format == "JPEG"
        assert small.size == (view.width, view.height)


def test_small_images_are_not_enlarged() -> None:
    view = view_shot(jpeg(Image.new("RGB", (600, 400))))
    assert (view.width, view.height) == (600, 400)


def test_portrait_orientation_is_applied() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to view
    view = view_shot(jpeg(Image.new("RGB", (1500, 1000)), exif=exif.tobytes()))
    assert view.width < view.height


def test_stats_report_clipping() -> None:
    white = histogram_stats(Image.new("RGB", (10, 10), (255, 255, 255)))
    black = histogram_stats(Image.new("RGB", (10, 10), (0, 0, 0)))
    assert white["clipped_highlights_percent"] == 100.0
    assert white["clipped_shadows_percent"] == 0.0
    assert white["channel_clipped_percent"] == {"red": 100.0, "green": 100.0, "blue": 100.0}
    assert black["clipped_shadows_percent"] == 100.0
    assert black["mean_luminance"] == 0.0
    assert black["luminance_histogram_percent"][0] == 100.0


def test_stats_of_a_split_image() -> None:
    image = Image.new("RGB", (10, 10), (0, 0, 0))
    image.paste((200, 50, 50), (0, 0, 10, 5))
    stats = histogram_stats(image)
    assert stats["clipped_shadows_percent"] == 50.0
    assert stats["channel_mean"]["red"] == 100.0
    assert sum(stats["luminance_histogram_percent"]) == pytest.approx(100.0)
    assert len(stats["luminance_histogram_percent"]) == 8


def test_shooting_data_from_the_mock_camera() -> None:
    camera = MockCamera(lang="en")
    camera.set("iso", "400")
    shooting = view_shot(camera.capture()[0].data).shooting
    assert shooting["exposure_time"] == "1/125 s"
    assert shooting["f_number"] == "f/5.6"
    assert shooting["iso"] == 400
    assert shooting["exposure_program"] == "manual"
    assert shooting["focal_length_mm"] == 18.0


def test_long_exposure_is_written_in_seconds() -> None:
    camera = MockCamera(lang="en")
    camera.set("shutterspeed2", "2")
    assert view_shot(camera.capture()[0].data).shooting["exposure_time"] == "2 s"


def test_missing_exif_gives_no_shooting_data() -> None:
    assert view_shot(jpeg(Image.new("RGB", (40, 30)))).shooting == {}


def test_not_a_jpeg_raises_oserror() -> None:
    with pytest.raises(OSError):
        view_shot(b"lensmind mock NEF: not a real raw file\n")


def test_latest_shot_picks_the_jpeg_of_the_newest_shot(tmp_path: Path) -> None:
    store = PhotoStore(tmp_path)
    assert latest_shot(store) is None
    older = store.save([CapturedFile("DSC_0001.JPG", jpeg(Image.new("RGB", (8, 8))))])
    newest = store.save(
        [CapturedFile("DSC_0002.NEF", b"raw"), CapturedFile("DSC_0002.JPG", b"jpg")]
    )
    for shot, when in ((older, 1_000), (newest, 2_000)):
        for name in shot.files:
            os.utime(tmp_path / name, (when, when))
    shot = latest_shot(store)
    assert shot is not None
    assert sorted(shot.files) == sorted(newest.files)
    assert shot.jpeg_name is not None and shot.jpeg_name.endswith("DSC_0002.JPG")
    assert shot.jpeg == b"jpg"
    assert shot.taken_at == 2_000


def test_latest_shot_without_jpeg(tmp_path: Path) -> None:
    store = PhotoStore(tmp_path)
    store.save([CapturedFile("DSC_0001.NEF", b"raw")])
    shot = latest_shot(store)
    assert shot is not None
    assert shot.jpeg is None and shot.jpeg_name is None
