"""Camera implementation on libgphoto2 (python-gphoto2). The only gphoto2 importer."""

# Postponed annotations: the `set` method below would shadow `set[str]` in the class body.
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from lensmind.camera.base import (
    EXCLUDED_SECTIONS,
    CameraDisconnected,
    CameraError,
    CameraStatus,
    CapturedFile,
    Setting,
    SettingGroup,
    SettingType,
    SettingValue,
    liveview_block_reason,
    validate,
)
from lensmind.camera.messages import msg

T = TypeVar("T")
# After capture, a RAW+JPEG second file arrives as GP_EVENT_FILE_ADDED.
SECOND_FILE_WAIT_SECONDS = 1.5


class GPhotoCamera:
    def __init__(self, lang: str = "it") -> None:
        import gphoto2 as gp  # lazy: mock mode must work without libgphoto2

        self._gp: Any = gp
        self._lang = lang
        self._types: dict[int, SettingType] = {
            gp.GP_WIDGET_RADIO: "choice",
            gp.GP_WIDGET_MENU: "choice",
            gp.GP_WIDGET_RANGE: "range",
            gp.GP_WIDGET_TOGGLE: "toggle",
            gp.GP_WIDGET_TEXT: "text",
            gp.GP_WIDGET_DATE: "date",
        }
        self._containers = {gp.GP_WIDGET_WINDOW, gp.GP_WIDGET_SECTION}
        self._liveview = False
        self._exposed: set[str] | None = None
        self._camera = gp.Camera()
        self._run(self._camera.init)

    # Camera protocol -----------------------------------------------------------

    def status(self) -> CameraStatus:
        abilities = self._run(self._camera.get_abilities)
        return CameraStatus(
            manufacturer=self._text("manufacturer") or "",
            model=self._text("cameramodel") or abilities.model,
            battery=self._text("batterylevel"),
            can_preview=bool(abilities.operations & self._gp.GP_OPERATION_CAPTURE_PREVIEW),
            liveview_active=self._liveview,
            liveview_blocked_reason=liveview_block_reason(self._text("liveviewprohibit")),
        )

    def settings(self) -> list[SettingGroup]:
        root = self._run(self._camera.get_config)
        groups: list[SettingGroup] = []
        seen: set[str] = set()
        for index in range(root.count_children()):
            section = root.get_child(index)
            if section.get_name() in EXCLUDED_SECTIONS:
                continue
            items: list[Setting] = []
            self._collect(section, items, seen)
            if items:
                groups.append(SettingGroup(section.get_name(), section.get_label(), items))
        self._exposed = seen
        return groups

    def set(self, name: str, value: SettingValue) -> Setting:
        if self._exposed is None:
            self.settings()
        assert self._exposed is not None
        widget = self._run(self._camera.get_single_config, name) if name in self._exposed else None
        # Re-read the widget: read-only flags and choices change with the dial and lens.
        current = self._to_setting(widget) if widget is not None else None
        coerced = validate(current, name, value, self._lang)
        self._run(widget.set_value, coerced)
        self._run(self._camera.set_single_config, name, widget)
        fresh = self._to_setting(self._run(self._camera.get_single_config, name))
        assert fresh is not None
        return fresh

    def capture(self) -> list[CapturedFile]:
        gp = self._gp
        try:
            self.end_liveview()
        except CameraDisconnected:
            raise
        except CameraError:
            # Nikon bodies refuse to end a live view that is not running (NotLiveView).
            # Only a live view we know is on must be stopped before shooting.
            if self._liveview:
                raise
        first = self._run(self._camera.capture, gp.GP_CAPTURE_IMAGE)
        paths = [(first.folder, first.name)]
        deadline = time.monotonic() + SECOND_FILE_WAIT_SECONDS
        while (remaining := deadline - time.monotonic()) > 0:
            event, data = self._run(self._camera.wait_for_event, max(1, int(remaining * 1000)))
            if event == gp.GP_EVENT_FILE_ADDED:
                paths.append((data.folder, data.name))
            elif event == gp.GP_EVENT_TIMEOUT:
                break
        files = []
        for folder, name in paths:
            camera_file = self._run(self._camera.file_get, folder, name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(memoryview(self._run(camera_file.get_data_and_size)))
            files.append(CapturedFile(name, data))
        return files

    def preview(self) -> bytes:
        if not self._liveview:
            reason = liveview_block_reason(self._text("liveviewprohibit"))
            if reason:
                raise CameraError(reason, 409)
        camera_file = self._run(self._camera.capture_preview)
        self._liveview = True
        return bytes(memoryview(self._run(camera_file.get_data_and_size)))

    def end_liveview(self) -> None:
        widget = self._single("viewfinder")
        if widget is not None:
            self._run(widget.set_value, 0)
            self._run(self._camera.set_single_config, "viewfinder", widget)
        self._liveview = False

    def close(self) -> None:
        try:
            self._camera.exit()
        except self._gp.GPhoto2Error:
            pass

    # Internals -----------------------------------------------------------------

    def _run(self, function: Callable[..., T], *args: object) -> T:
        try:
            return function(*args)
        except self._gp.GPhoto2Error as error:
            raise self._translate(error) from error

    def _translate(self, error: Any) -> CameraError:
        gp, lang, code = self._gp, self._lang, error.code
        if code == gp.GP_ERROR_BAD_PARAMETERS:
            return CameraError(msg(lang, "bad_parameters"), 422)
        if code == gp.GP_ERROR_NOT_SUPPORTED:
            return CameraError(msg(lang, "not_supported"), 409)
        if code == gp.GP_ERROR_CAMERA_BUSY:
            return CameraError(msg(lang, "camera_busy"), 503)
        if code == gp.GP_ERROR:
            return CameraError(msg(lang, "camera_error", error=error), 500)
        if code == gp.GP_ERROR_MODEL_NOT_FOUND:
            return CameraDisconnected(msg(lang, "not_connected"), 503)
        if code == gp.GP_ERROR_IO_USB_CLAIM:
            return CameraDisconnected(msg(lang, "usb_claimed"), 503)
        return CameraDisconnected(msg(lang, "io_error", error=error), 503)

    def _single(self, name: str) -> Any | None:
        """The widget called `name`, or None when the camera does not have it."""
        gp = self._gp
        try:
            return self._camera.get_single_config(name)
        except gp.GPhoto2Error as error:
            if error.code in (gp.GP_ERROR_BAD_PARAMETERS, gp.GP_ERROR_NOT_SUPPORTED, gp.GP_ERROR):
                return None
            raise self._translate(error) from error

    def _text(self, name: str) -> str | None:
        widget = self._single(name)
        if widget is None:
            return None
        value = widget.get_value()
        return None if value is None else str(value)

    def _collect(self, widget: Any, out: list[Setting], seen: set[str]) -> None:
        for index in range(widget.count_children()):
            child = widget.get_child(index)
            if child.get_type() in self._containers:
                self._collect(child, out, seen)
                continue
            setting = self._to_setting(child)
            if setting is not None and setting.name not in seen:
                seen.add(setting.name)
                out.append(setting)

    def _to_setting(self, widget: Any) -> Setting | None:
        kind = self._types.get(widget.get_type())
        if kind is None:
            return None
        raw = widget.get_value()
        choices: list[str] | None = None
        low = high = step = None
        value: SettingValue
        if kind == "choice":
            choices = [widget.get_choice(i) for i in range(widget.count_choices())]
            value = "" if raw is None else str(raw)
        elif kind == "range":
            low, high, step = (float(n) for n in widget.get_range())
            value = float(raw)
        elif kind in ("toggle", "date"):
            value = int(raw)
        else:
            value = "" if raw is None else str(raw)
        return Setting(
            name=widget.get_name(),
            label=widget.get_label(),
            type=kind,
            value=value,
            readonly=bool(widget.get_readonly()),
            choices=choices,
            min=low,
            max=high,
            step=step,
        )
