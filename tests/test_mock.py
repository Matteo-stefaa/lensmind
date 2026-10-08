import io
import math

import pytest
from PIL import Image, ImageStat

from lensmind.camera.base import CameraDisconnected, CameraError, Setting
from lensmind.camera.mock import MockCamera


@pytest.fixture
def cam() -> MockCamera:
    return MockCamera(dial="M", lang="en")


def get(cam: MockCamera, name: str) -> Setting:
    return next(s for group in cam.settings() for s in group.settings if s.name == name)


def mean(data: bytes) -> float:
    with Image.open(io.BytesIO(data)) as image:
        return ImageStat.Stat(image.convert("L")).mean[0]


def test_status(cam: MockCamera) -> None:
    status = cam.status()
    assert status.model == "D3500"
    assert status.manufacturer == "Nikon Corporation"
    assert status.can_preview
    assert not status.liveview_active
    assert status.liveview_blocked_reason is None


def test_set_validates_like_a_real_camera(cam: MockCamera) -> None:
    for name, value, status in [
        ("iso", "123", 422),
        ("opcode", "0x1001", 404),
        ("batterylevel", "1%", 409),
    ]:
        with pytest.raises(CameraError) as caught:
            cam.set(name, value)
        assert caught.value.status == status


def test_every_writable_type_round_trips(cam: MockCamera) -> None:
    cam.set("iso", "400")
    cam.set("burstnumber", 5)
    cam.set("fastfs", 0)
    cam.set("artist", "Matteo")
    cam.set("datetime", 1800000000)
    assert get(cam, "iso").value == "400"
    assert get(cam, "burstnumber").value == 5.0
    assert get(cam, "fastfs").value == 0
    assert get(cam, "artist").value == "Matteo"
    assert get(cam, "datetime").value == 1800000000


def test_shutter_names_stay_in_sync(cam: MockCamera) -> None:
    cam.set("shutterspeed2", "1/30")
    assert get(cam, "shutterspeed").value == "0.0333s"
    cam.set("shutterspeed", "0.0080s")
    assert get(cam, "shutterspeed2").value == "1/125"


def test_bulb_and_time_do_not_break_exposure(cam: MockCamera) -> None:
    for speed in ("Bulb", "Time"):
        cam.set("shutterspeed2", speed)
        assert get(cam, "shutterspeed").value == speed
        assert math.isfinite(cam.exposure_error())
        assert cam.capture()


def test_auto_exposure_never_picks_bulb(cam: MockCamera) -> None:
    cam.turn_dial("A")
    cam.set("f-number", "f/22")
    cam.set("iso", "100")
    cam.set("exposurecompensation", "5")
    assert get(cam, "shutterspeed2").value not in ("Bulb", "Time")


def test_initial_exposure_is_about_right(cam: MockCamera) -> None:
    assert abs(cam.exposure_error()) < 0.3


def test_longer_shutter_overexposes(cam: MockCamera) -> None:
    before = cam.exposure_error()
    cam.set("shutterspeed2", "1/30")
    assert cam.exposure_error() - before == pytest.approx(2.06, abs=0.01)


def test_dial_a_locks_shutter_and_meters(cam: MockCamera) -> None:
    cam.turn_dial("A")
    assert get(cam, "shutterspeed2").readonly
    assert not get(cam, "f-number").readonly
    assert get(cam, "expprogram").value == "A"
    cam.set("f-number", "f/11")
    assert abs(cam.exposure_error()) < 0.2


def test_dial_a_follows_exposure_compensation(cam: MockCamera) -> None:
    cam.turn_dial("A")
    cam.set("exposurecompensation", "1")
    assert cam.exposure_error() == pytest.approx(1.0, abs=0.2)


def test_dial_auto_blocks_liveview_and_locks_exposure(cam: MockCamera) -> None:
    cam.turn_dial("AUTO")
    assert get(cam, "f-number").readonly
    assert get(cam, "shutterspeed2").readonly
    assert get(cam, "f-number").choices[0] == "f/1"
    assert abs(cam.exposure_error()) < 0.2
    with pytest.raises(CameraError) as caught:
        cam.preview()
    assert caught.value.status == 409
    assert "P/A/S/M" in caught.value.message
    assert cam.status().liveview_blocked_reason is not None


def test_dial_back_to_m_restores_lens_apertures(cam: MockCamera) -> None:
    cam.turn_dial("AUTO")
    cam.turn_dial("M")
    assert get(cam, "f-number").choices[0] == "f/3.5"
    assert not get(cam, "shutterspeed2").readonly


def test_turn_dial_rejects_unknown_mode(cam: MockCamera) -> None:
    with pytest.raises(ValueError):
        cam.turn_dial("S")


def test_preview_returns_jpeg_and_tracks_liveview(cam: MockCamera) -> None:
    assert cam.preview()[:2] == b"\xff\xd8"
    assert cam.status().liveview_active
    cam.end_liveview()
    assert not cam.status().liveview_active


def test_capture_raw_plus_jpeg_gives_two_files(cam: MockCamera) -> None:
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG", "DSC_0001.NEF"]


def test_capture_jpeg_only_and_numbering(cam: MockCamera) -> None:
    cam.set("imagequality", "JPEG Fine")
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG"]
    assert [f.name for f in cam.capture()] == ["DSC_0002.JPG"]


def test_capture_turns_liveview_off(cam: MockCamera) -> None:
    cam.preview()
    cam.capture()
    assert not cam.status().liveview_active


def test_captured_brightness_follows_settings(cam: MockCamera) -> None:
    cam.set("imagequality", "JPEG Fine")
    cam.set("shutterspeed2", "1/4000")
    dark = mean(cam.capture()[0].data)
    cam.set("shutterspeed2", "1/8")
    bright = mean(cam.capture()[0].data)
    assert dark < bright


def test_simulate_disconnect_fails_next_call_only(cam: MockCamera) -> None:
    cam.simulate_disconnect()
    with pytest.raises(CameraDisconnected):
        cam.status()
    assert cam.status().model == "D3500"


def test_close(cam: MockCamera) -> None:
    cam.close()
    assert cam.closed
