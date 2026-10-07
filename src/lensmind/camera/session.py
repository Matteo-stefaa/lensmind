"""One camera, one command at a time: locking, lazy reconnection, idle live view."""

import logging
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from lensmind.camera.base import (
    Camera,
    CameraDisconnected,
    CameraError,
    CameraStatus,
    CapturedFile,
    Setting,
    SettingGroup,
    SettingValue,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CameraSession:
    """Implements `Camera` on top of a camera created on demand by `factory`."""

    def __init__(
        self,
        factory: Callable[[], Camera],
        idle_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        watchdog_interval: float = 1.0,
    ) -> None:
        self._factory = factory
        self._idle_seconds = idle_seconds
        self._clock = clock
        self._interval = watchdog_interval
        self._lock = threading.RLock()
        self._camera: Camera | None = None
        self._liveview = False
        self._last_preview = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # Watchdog ------------------------------------------------------------------

    def start_watchdog(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._watch, name="liveview-watchdog", daemon=True
            )
            self._thread.start()

    def _watch(self) -> None:
        while not self._stop.wait(self._interval):
            self.check_idle()

    def check_idle(self) -> None:
        """Turn live view off when no preview was requested for `idle_seconds`."""
        with self._lock:
            if not self._liveview or self._clock() - self._last_preview <= self._idle_seconds:
                return
            try:
                self.end_liveview()
            except CameraError:
                logger.warning("could not stop idle live view", exc_info=True)

    # Camera protocol -----------------------------------------------------------

    def status(self) -> CameraStatus:
        return self._call(lambda camera: camera.status())

    def settings(self) -> list[SettingGroup]:
        return self._call(lambda camera: camera.settings())

    def set(self, name: str, value: SettingValue) -> Setting:
        return self._call(lambda camera: camera.set(name, value))

    def capture(self) -> list[CapturedFile]:
        with self._lock:
            if self._liveview:
                self.end_liveview()
            return self._call(lambda camera: camera.capture())

    def preview(self) -> bytes:
        with self._lock:
            frame = self._call(lambda camera: camera.preview())
            self._liveview = True
            self._last_preview = self._clock()
            return frame

    def end_liveview(self) -> None:
        with self._lock:
            if self._camera is not None:
                self._call(lambda camera: camera.end_liveview())
            self._liveview = False

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.close()
                finally:
                    self._camera = None

    # Internals -----------------------------------------------------------------

    def _call(self, action: Callable[[Camera], T]) -> T:
        with self._lock:
            if self._camera is None:
                self._camera = self._factory()
            try:
                return action(self._camera)
            except CameraDisconnected:
                self._drop()
                raise

    def _drop(self) -> None:
        camera, self._camera = self._camera, None
        self._liveview = False
        if camera is not None:
            try:
                camera.close()
            except Exception:
                logger.debug("closing a disconnected camera failed", exc_info=True)
