import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import fake_gphoto2
import pytest

from lensmind.camera.base import CameraDisconnected, CameraError, Setting

DUMPS = Path(__file__).resolve().parents[1] / "docs" / "cameras" / "d3500"


@pytest.fixture
def gp(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    fake_gphoto2.reset(DUMPS / "d3500-config-M.txt")
    monkeypatch.setitem(sys.modules, "gphoto2", fake_gphoto2)
    yield fake_gphoto2


def use_dump(mode: str) -> None:
    fake_gphoto2.reset(DUMPS / f"d3500-config-{mode}.txt")


def open_camera() -> Any:
    from lensmind.camera.gphoto import GPhotoCamera

    return GPhotoCamera(lang="en")


@pytest.fixture
def cam(gp: ModuleType) -> Any:
    return open_camera()


def by_name(cam: Any, name: str) -> Setting:
    return next(s for g in cam.settings() for s in g.settings if s.name == name)


def fake() -> Any:
    assert fake_gphoto2.last_camera is not None
    return fake_gphoto2.last_camera


def test_module_does_not_import_gphoto2_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "gphoto2", raising=False)
    import lensmind.camera.gphoto as module

    importlib.reload(module)
    assert "gphoto2" not in sys.modules


def test_no_camera_is_a_disconnection(gp: ModuleType) -> None:
    fake_gphoto2.INIT_ERROR = gp.GP_ERROR_MODEL_NOT_FOUND
    with pytest.raises(CameraDisconnected) as caught:
        open_camera()
    assert caught.value.status == 503
    assert "not connected" in caught.value.message


def test_usb_claim_explains_the_cause(gp: ModuleType) -> None:
    fake_gphoto2.INIT_ERROR = gp.GP_ERROR_IO_USB_CLAIM
    with pytest.raises(CameraDisconnected) as caught:
        open_camera()
    assert "another process" in caught.value.message


def test_settings_exclude_actions_and_other(cam: Any) -> None:
    groups = cam.settings()
    assert [g.name for g in groups] == ["settings", "status", "imgsettings", "capturesettings"]
    names = [s.name for g in groups for s in g.settings]
    assert len(names) == 50
    assert len(set(names)) == 50


def test_settings_types_and_values(cam: Any) -> None:
    aperture = by_name(cam, "f-number")
    burst = by_name(cam, "burstnumber")
    assert aperture.type == "choice" and aperture.choices and aperture.choices[0] == "f/3.5"
    assert (burst.type, burst.min, burst.max, burst.step, burst.value) == ("range", 1, 100, 1, 1.0)
    assert by_name(cam, "fastfs").type == "toggle"
    assert isinstance(by_name(cam, "datetime").value, int)
    assert by_name(cam, "batterylevel").readonly


def test_set_writes_the_converted_value(cam: Any) -> None:
    assert cam.set("burstnumber", 3).value == 3.0
    assert ("set_single_config", "burstnumber", 3.0) in fake().log
    assert cam.set("iso", "200").value == "200"


def test_set_rejects_value_outside_lens_range(cam: Any) -> None:
    with pytest.raises(CameraError) as caught:
        cam.set("f-number", "f/1.8")
    assert caught.value.status == 422
    assert "f/3.5" in caught.value.message
    assert not any(entry[0] == "set_single_config" for entry in fake().log)


def test_set_reads_fresh_readonly_flags(gp: ModuleType) -> None:
    use_dump("AUTO")
    cam = open_camera()
    with pytest.raises(CameraError) as caught:
        cam.set("f-number", "f/5.6")
    assert caught.value.status == 409


@pytest.mark.parametrize("name", ["opcode", "viewfinder", "5007", "nope"])
def test_set_refuses_hidden_or_unknown_names(cam: Any, name: str) -> None:
    with pytest.raises(CameraError) as caught:
        cam.set(name, "1")
    assert caught.value.status == 404


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("GP_ERROR_CAMERA_BUSY", 503),
        ("GP_ERROR_BAD_PARAMETERS", 422),
        ("GP_ERROR_NOT_SUPPORTED", 409),
        ("GP_ERROR", 500),
    ],
)
def test_soft_errors_keep_the_connection(cam: Any, gp: ModuleType, code: str, status: int) -> None:
    cam.settings()
    fake().fail_next["set_single_config"] = getattr(gp, code)
    with pytest.raises(CameraError) as caught:
        cam.set("iso", "200")
    assert not isinstance(caught.value, CameraDisconnected)
    assert caught.value.status == status


def test_io_error_is_a_disconnection(cam: Any, gp: ModuleType) -> None:
    fake().fail_next["get_config"] = gp.GP_ERROR_IO
    with pytest.raises(CameraDisconnected):
        cam.settings()


def test_status(cam: Any) -> None:
    status = cam.status()
    assert status.manufacturer == "Nikon Corporation"
    assert status.model == "D3500"
    assert status.battery == "20%"
    assert status.can_preview
    assert status.liveview_blocked_reason is None


def test_status_reports_liveview_block_in_auto(gp: ModuleType) -> None:
    use_dump("AUTO")
    reason = open_camera().status().liveview_blocked_reason
    assert reason is not None and "P/A/S/M" in reason


def test_preview_refused_in_auto(gp: ModuleType) -> None:
    use_dump("AUTO")
    cam = open_camera()
    with pytest.raises(CameraError) as caught:
        cam.preview()
    assert caught.value.status == 409
    assert ("capture_preview",) not in fake().log


def test_preview_returns_a_frame(cam: Any) -> None:
    assert cam.preview()[:2] == b"\xff\xd8"
    assert cam.status().liveview_active


def test_end_liveview_turns_viewfinder_off(cam: Any) -> None:
    cam.preview()
    cam.end_liveview()
    assert ("set_single_config", "viewfinder", 0) in fake().log
    assert not cam.status().liveview_active


NIKON_SHOT = "0x9207,0xfffffffe,0x1"


def as_other_brand() -> None:
    """Make the fake report a non-Nikon body, so capture goes through camera.capture()."""
    manufacturer = fake()._find(fake().root, "manufacturer")
    assert manufacturer is not None
    manufacturer.value = "Canon Inc."


def nikon_shot(gp: ModuleType, *names: str) -> list[tuple[int, object]]:
    folder = "/store_00010001/DCIM/100D3500"
    files = [(gp.GP_EVENT_FILE_ADDED, gp.CameraFilePath(folder, n)) for n in names]
    return [*files, (gp.GP_EVENT_CAPTURE_COMPLETE, None)]


def test_nikon_capture_sends_the_command_and_collects_the_files(cam: Any, gp: ModuleType) -> None:
    # Verified on a D3500: libgphoto2's capture() can wait forever for DeviceReady after
    # an autofocus shot; sending InitiateCaptureRecInMedia and reading events does not.
    fake().capture_events = nikon_shot(gp, "DSC_0001.JPG", "DSC_0001.NEF")
    files = cam.capture()
    assert [f.name for f in files] == ["DSC_0001.JPG", "DSC_0001.NEF"]
    assert files[0].data == b"data:DSC_0001.JPG"
    entries = fake().log
    viewfinder_off = entries.index(("set_single_config", "viewfinder", 0))
    assert viewfinder_off < entries.index(("opcode", NIKON_SHOT))
    assert ("capture", gp.GP_CAPTURE_IMAGE) not in entries


def test_nikon_capture_to_the_memory_card_targets_the_card(cam: Any) -> None:
    cam.set("capturetarget", "Memory card")
    cam.capture()
    assert ("opcode", "0x9207,0xfffffffe,0x0") in fake().log


def test_nikon_capture_refused_by_the_body_is_explained(cam: Any, gp: ModuleType) -> None:
    # The opcode widget reports every Nikon response (e.g. Out of Focus, 0xa002) as a
    # bare GP_ERROR, so the cause can only be suggested.
    fake().fail_next["opcode"] = gp.GP_ERROR
    with pytest.raises(CameraError) as caught:
        cam.capture()
    assert not isinstance(caught.value, CameraDisconnected)
    assert caught.value.status == 409
    assert "refused" in caught.value.message


def test_nikon_capture_without_files_times_out_and_reconnects(
    cam: Any, gp: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lensmind.camera.gphoto as module

    monkeypatch.setattr(module, "CAPTURE_TIMEOUT_SECONDS", 0.05)
    fake().capture_events = [(gp.GP_EVENT_UNKNOWN, "property changed")]
    with pytest.raises(CameraDisconnected) as caught:
        cam.capture()
    assert caught.value.status == 504


def test_nikon_capture_falls_back_when_the_command_is_unsupported(cam: Any, gp: ModuleType) -> None:
    fake().fail_next["opcode"] = gp.GP_ERROR_NOT_SUPPORTED
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG"]
    assert ("capture", gp.GP_CAPTURE_IMAGE) in fake().log
    fake().log.clear()
    cam.capture()
    assert not any(entry[0] == "opcode" for entry in fake().log)


def test_capture_deletes_files_left_from_an_earlier_shot(cam: Any, gp: ModuleType) -> None:
    # Verified on a D3500: a NEF not downloaded stays in Internal RAM, comes back as
    # GP_EVENT_FILE_ADDED in a later session, and would be taken for this shot's file.
    stale = gp.CameraFilePath("/", "capt0000.nef")
    fake().events = [(gp.GP_EVENT_FILE_ADDED, stale)]
    files = cam.capture()
    assert [f.name for f in files] == ["DSC_0001.JPG"]
    entries = fake().log
    deleted = entries.index(("file_delete", "/", "capt0000.nef"))
    assert deleted < entries.index(("opcode", NIKON_SHOT))
    assert ("file_get", "/", "capt0000.nef") not in entries


def test_generic_capture_collects_raw(cam: Any, gp: ModuleType) -> None:
    as_other_brand()
    raw = gp.CameraFilePath("/store_00010001/DCIM/100D3500", "DSC_0001.NEF")
    fake().capture_events = [(gp.GP_EVENT_FILE_ADDED, raw)]
    files = cam.capture()
    assert [f.name for f in files] == ["DSC_0001.JPG", "DSC_0001.NEF"]
    assert not any(entry[0] == "opcode" for entry in fake().log)


def test_capture_out_of_focus_explains_the_cause(cam: Any, gp: ModuleType) -> None:
    # Verified on a D3500 in AF-A: the body refuses to release and libgphoto2 returns
    # GP_ERROR; only the context carries "Out of Focus" (PTP 0xa002).
    as_other_brand()
    fake().fail_next["capture"] = gp.GP_ERROR
    fake().fail_text["capture"] = "Out of Focus"
    with pytest.raises(CameraError) as caught:
        cam.capture()
    assert not isinstance(caught.value, CameraDisconnected)
    assert caught.value.status == 409
    assert "could not focus" in caught.value.message


def test_generic_error_carries_the_driver_text(cam: Any, gp: ModuleType) -> None:
    as_other_brand()
    fake().fail_next["capture"] = gp.GP_ERROR
    fake().fail_text["capture"] = "Card full"
    with pytest.raises(CameraError) as caught:
        cam.capture()
    assert caught.value.status == 500
    assert "Card full" in caught.value.message


def test_driver_text_does_not_leak_into_the_next_error(cam: Any, gp: ModuleType) -> None:
    as_other_brand()
    fake().fail_next["capture"] = gp.GP_ERROR
    fake().fail_text["capture"] = "Out of Focus"
    with pytest.raises(CameraError):
        cam.capture()
    fake().fail_next["capture"] = gp.GP_ERROR
    with pytest.raises(CameraError) as caught:
        cam.capture()
    assert caught.value.status == 500
    assert "could not focus" not in caught.value.message


def test_close_swallows_errors(cam: Any, gp: ModuleType) -> None:
    fake().fail_next["exit"] = gp.GP_ERROR_IO
    cam.close()


def test_capture_without_liveview_succeeds_on_a_strict_body(cam: Any) -> None:
    files = cam.capture()
    assert [f.name for f in files] == ["DSC_0001.JPG"]


def test_capture_after_session_ended_liveview_succeeds(cam: Any) -> None:
    cam.preview()
    cam.end_liveview()
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG"]


def test_capture_during_liveview_ends_it_first(cam: Any) -> None:
    cam.preview()
    cam.capture()
    assert not fake().in_liveview


def test_missing_libgphoto2_is_reported_as_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "gphoto2", None)  # makes `import gphoto2` fail
    with pytest.raises(CameraDisconnected) as caught:
        open_camera()
    assert caught.value.status == 503
    assert "LENSMIND_MOCK=1" in caught.value.message
