"""In-memory stand-in for python-gphoto2, built from a real `--list-all-config` dump."""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lensmind.camera.dump import parse_dump

GP_OK = 0
GP_ERROR = -1
GP_ERROR_BAD_PARAMETERS = -2
GP_ERROR_NOT_SUPPORTED = -6
GP_ERROR_IO = -7
GP_ERROR_IO_USB_CLAIM = -53
GP_ERROR_MODEL_NOT_FOUND = -105
GP_ERROR_CAMERA_BUSY = -110

(
    GP_WIDGET_WINDOW,
    GP_WIDGET_SECTION,
    GP_WIDGET_TEXT,
    GP_WIDGET_RANGE,
    GP_WIDGET_TOGGLE,
    GP_WIDGET_RADIO,
    GP_WIDGET_MENU,
    GP_WIDGET_BUTTON,
    GP_WIDGET_DATE,
) = range(9)
GP_CAPTURE_IMAGE = 0
GP_FILE_TYPE_NORMAL = 1
GP_EVENT_UNKNOWN, GP_EVENT_TIMEOUT, GP_EVENT_FILE_ADDED = 0, 1, 2
GP_OPERATION_CONFIG = 1
GP_OPERATION_CAPTURE_PREVIEW = 8

_TYPES = {
    "WINDOW": GP_WIDGET_WINDOW,
    "SECTION": GP_WIDGET_SECTION,
    "TEXT": GP_WIDGET_TEXT,
    "RANGE": GP_WIDGET_RANGE,
    "TOGGLE": GP_WIDGET_TOGGLE,
    "RADIO": GP_WIDGET_RADIO,
    "MENU": GP_WIDGET_MENU,
    "BUTTON": GP_WIDGET_BUTTON,
    "DATE": GP_WIDGET_DATE,
}
_VALUE_TYPES = {
    GP_WIDGET_TEXT: str,
    GP_WIDGET_RADIO: str,
    GP_WIDGET_MENU: str,
    GP_WIDGET_RANGE: float,
    GP_WIDGET_TOGGLE: int,
    GP_WIDGET_DATE: int,
}

# Set by tests (via reset) before creating a Camera.
DUMP_PATH: Path | None = None
INIT_ERROR: int | None = None
last_camera: "Camera | None" = None


def reset(dump_path: Path) -> None:
    global DUMP_PATH, INIT_ERROR, last_camera
    DUMP_PATH, INIT_ERROR, last_camera = dump_path, None, None


class GPhoto2Error(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"[{code}] fake gphoto2 error")
        self.code = code


ErrorFunc = Callable[[object, bytes, object], None]


class Context:
    """Like gp.Context: the camera driver reports the cause of a failure through it."""

    def __init__(self) -> None:
        self._error_func: ErrorFunc | None = None
        self._data: object = None

    def set_error_func(self, func: ErrorFunc, data: object) -> object:
        self._error_func, self._data = func, data
        return object()

    def error(self, text: str) -> None:
        if self._error_func is not None:
            self._error_func(self, text.encode(), self._data)


def _check_types(camera_file: object, context: object) -> None:
    """Catch arguments in the wrong position, as the SWIG bindings do."""
    if camera_file is not None and not isinstance(camera_file, CameraFile):
        raise TypeError(f"expected CameraFile, got {type(camera_file).__name__}")
    if context is not None and not isinstance(context, Context):
        raise TypeError(f"expected Context, got {type(context).__name__}")


class CameraWidget:
    def __init__(
        self,
        name: str,
        label: str,
        type_: int,
        value: object = None,
        readonly: bool = False,
        choices: tuple[str, ...] = (),
        range_: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.name, self.label, self.type, self.value = name, label, type_, value
        self.readonly, self.choices, self.range = readonly, choices, range_
        self.children: list[CameraWidget] = []

    def get_name(self) -> str:
        return self.name

    def get_label(self) -> str:
        return self.label

    def get_type(self) -> int:
        return self.type

    def get_value(self) -> object:
        return self.value

    def set_value(self, value: object) -> None:
        expected = _VALUE_TYPES[self.type]
        if type(value) is not expected:
            raise TypeError(
                f"{self.name}: expected {expected.__name__}, got {type(value).__name__}"
            )
        self.value = value

    def get_readonly(self) -> int:
        return int(self.readonly)

    def count_children(self) -> int:
        return len(self.children)

    def get_child(self, index: int) -> "CameraWidget":
        return self.children[index]

    def count_choices(self) -> int:
        return len(self.choices)

    def get_choice(self, index: int) -> str:
        return self.choices[index]

    def get_range(self) -> tuple[float, float, float]:
        return self.range


def _value(type_: int, current: str) -> object:
    if type_ == GP_WIDGET_RANGE:
        return float(current)
    if type_ in (GP_WIDGET_TOGGLE, GP_WIDGET_DATE):
        return int(current)
    return current


def build_tree(path: Path) -> CameraWidget:
    root = CameraWidget("main", "Camera and Driver Configuration", GP_WIDGET_WINDOW)
    sections: dict[str, CameraWidget] = {}
    for entry in parse_dump(path.read_text(encoding="utf-8")):
        section = sections.get(entry.section)
        if section is None:
            section = CameraWidget(entry.section, entry.section, GP_WIDGET_SECTION)
            sections[entry.section] = section
            root.children.append(section)
        type_ = _TYPES[entry.type]
        section.children.append(
            CameraWidget(
                entry.name,
                entry.label,
                type_,
                _value(type_, entry.current),
                entry.readonly,
                entry.choices,
                (entry.bottom or 0.0, entry.top or 0.0, entry.step or 0.0),
            )
        )
    return root


@dataclass
class CameraFilePath:
    folder: str
    name: str


class CameraFile:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def get_data_and_size(self) -> bytes:
        return self._data


@dataclass
class CameraAbilities:
    model: str = "Nikon DSC D3500"
    operations: int = GP_OPERATION_CONFIG | GP_OPERATION_CAPTURE_PREVIEW


class Camera:
    def __init__(self) -> None:
        global last_camera
        assert DUMP_PATH is not None, "call fake_gphoto2.reset(dump) first"
        self.root = build_tree(DUMP_PATH)
        self.log: list[tuple[object, ...]] = []
        self.fail_next: dict[str, int] = {}
        # Text the driver sends to the context when the matching fail_next fires.
        self.fail_text: dict[str, str] = {}
        self.events: list[tuple[int, object]] = []
        self.abilities = CameraAbilities()
        # Like a Nikon body: ending live view when it is not running is refused.
        self.in_liveview = False
        last_camera = self

    def _call(self, method: str, *args: object, context: Context | None = None) -> None:
        self.log.append((method, *args))
        code = self.fail_next.pop(method, None)
        if code is not None:
            text = self.fail_text.pop(method, None)
            if text is not None and context is not None:
                context.error(text)
            raise GPhoto2Error(code)

    def init(self, context: Context | None = None) -> None:
        self._call("init", context=context)
        if INIT_ERROR is not None:
            raise GPhoto2Error(INIT_ERROR)

    def exit(self, context: Context | None = None) -> None:
        self._call("exit", context=context)

    def get_abilities(self) -> CameraAbilities:
        self._call("get_abilities")
        return self.abilities

    def get_config(self, context: Context | None = None) -> CameraWidget:
        self._call("get_config", context=context)
        return self.root

    def get_single_config(self, name: str, context: Context | None = None) -> CameraWidget:
        self._call("get_single_config", name, context=context)
        widget = self._find(self.root, name)
        if widget is None:
            raise GPhoto2Error(GP_ERROR_BAD_PARAMETERS)
        return copy.copy(widget)

    def set_single_config(
        self, name: str, widget: CameraWidget, context: Context | None = None
    ) -> None:
        self._call("set_single_config", name, widget.get_value(), context=context)
        target = self._find(self.root, name)
        if target is None:
            raise GPhoto2Error(GP_ERROR_BAD_PARAMETERS)
        if name == "viewfinder" and widget.get_value() == 0:
            if not self.in_liveview:
                raise GPhoto2Error(GP_ERROR)  # PTP NotLiveView, reported as a generic error
            self.in_liveview = False
        target.value = widget.get_value()

    def capture(self, kind: int, context: Context | None = None) -> CameraFilePath:
        self._call("capture", kind, context=context)
        return CameraFilePath("/store_00010001/DCIM/100D3500", "DSC_0001.JPG")

    def wait_for_event(self, timeout_ms: int, context: Context | None = None) -> tuple[int, object]:
        self._call("wait_for_event", context=context)
        return self.events.pop(0) if self.events else (GP_EVENT_TIMEOUT, None)

    # Like python-gphoto2: an optional output CameraFile comes before the context.
    def file_get(
        self,
        folder: str,
        name: str,
        kind: int,
        camera_file: CameraFile | None = None,
        context: Context | None = None,
    ) -> CameraFile:
        _check_types(camera_file, context)
        self._call("file_get", folder, name, context=context)
        return CameraFile(f"data:{name}".encode())

    def capture_preview(
        self, camera_file: CameraFile | None = None, context: Context | None = None
    ) -> CameraFile:
        _check_types(camera_file, context)
        self._call("capture_preview", context=context)
        self.in_liveview = True
        return CameraFile(b"\xff\xd8fake-preview\xff\xd9")

    def _find(self, widget: CameraWidget, name: str) -> CameraWidget | None:
        for child in widget.children:
            if child.type in (GP_WIDGET_WINDOW, GP_WIDGET_SECTION):
                found = self._find(child, name)
                if found is not None:
                    return found
            elif child.name == name:
                return child
        return None
