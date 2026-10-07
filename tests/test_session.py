import threading
import time

import pytest

from lensmind.camera.base import CameraDisconnected, CameraError, CameraStatus, CapturedFile
from lensmind.camera.mock import MockCamera
from lensmind.camera.session import CameraSession


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class RecordingCamera(MockCamera):
    def __init__(self) -> None:
        super().__init__(lang="en")
        self.calls: list[str] = []

    def preview(self) -> bytes:
        self.calls.append("preview")
        return super().preview()

    def end_liveview(self) -> None:
        self.calls.append("end_liveview")
        super().end_liveview()

    def capture(self) -> list[CapturedFile]:
        self.calls.append("capture")
        return super().capture()


def make_session(clock: Clock | None = None) -> tuple[CameraSession, list[RecordingCamera]]:
    created: list[RecordingCamera] = []

    def factory() -> RecordingCamera:
        camera = RecordingCamera()
        created.append(camera)
        return camera

    return CameraSession(factory, idle_seconds=5, clock=clock or Clock()), created


def test_connects_lazily_and_once() -> None:
    session, created = make_session()
    assert created == []
    session.status()
    session.settings()
    assert len(created) == 1


def test_reconnects_after_disconnect() -> None:
    session, created = make_session()
    session.status()
    created[0].simulate_disconnect()
    with pytest.raises(CameraDisconnected):
        session.status()
    assert created[0].closed
    assert session.status().model == "D3500"
    assert len(created) == 2


def test_soft_error_keeps_connection() -> None:
    session, created = make_session()
    with pytest.raises(CameraError) as caught:
        session.set("iso", "123")
    assert caught.value.status == 422
    session.status()
    assert len(created) == 1


def test_factory_failure_is_reported_then_retried() -> None:
    attempts: list[int] = []

    def flaky() -> MockCamera:
        attempts.append(1)
        if len(attempts) == 1:
            raise CameraDisconnected("Camera not connected", 503)
        return MockCamera(lang="en")

    session = CameraSession(flaky, idle_seconds=5)
    with pytest.raises(CameraDisconnected):
        session.status()
    assert session.status().model == "D3500"


def test_capture_ends_liveview_first() -> None:
    session, created = make_session()
    session.preview()
    session.capture()
    assert created[0].calls == ["preview", "end_liveview", "capture"]


def test_preview_after_capture_restarts_liveview() -> None:
    session, created = make_session()
    session.preview()
    files = session.capture()
    assert files
    assert session.preview()[:2] == b"\xff\xd8"
    assert created[0].status().liveview_active


def test_watchdog_stops_idle_liveview() -> None:
    clock = Clock()
    session, created = make_session(clock)
    session.preview()
    clock.now = 4.0
    session.check_idle()
    assert created[0].status().liveview_active
    clock.now = 5.1
    session.check_idle()
    assert not created[0].status().liveview_active


def test_watchdog_does_not_connect_an_idle_session() -> None:
    session, created = make_session()
    session.check_idle()
    assert created == []


def test_calls_are_serialised() -> None:
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    class SlowCamera(MockCamera):
        def status(self) -> CameraStatus:
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.01)
            with guard:
                state["active"] -= 1
            return super().status()

    session = CameraSession(lambda: SlowCamera(lang="en"), idle_seconds=5)
    threads = [threading.Thread(target=session.status) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert state["peak"] == 1


def test_watchdog_thread_runs_and_stops() -> None:
    clock = Clock()
    camera = MockCamera(lang="en")
    session = CameraSession(lambda: camera, idle_seconds=1, clock=clock, watchdog_interval=0.01)
    session.preview()
    clock.now = 2.0
    session.start_watchdog()
    deadline = time.monotonic() + 2
    while camera.status().liveview_active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not camera.status().liveview_active
    session.close()
    assert camera.closed
