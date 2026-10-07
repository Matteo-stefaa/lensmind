"""Camera protocol, data models, errors and the validation shared by all cameras."""

from dataclasses import dataclass
from typing import Literal, Protocol

from lensmind.camera.messages import msg

SettingValue = str | float | int
SettingType = Literal["choice", "range", "toggle", "text", "date"]

# Top-level config sections never exposed: raw PTP properties ("other") and actions
# such as "opcode", which sends arbitrary PTP commands to the camera.
EXCLUDED_SECTIONS = frozenset({"actions", "other"})

# Wording used by libgphoto2's Nikon driver in the "liveviewprohibit" status text.
LIVEVIEW_PROHIBIT_PREFIX = "Live View prohibit conditions"


@dataclass(frozen=True)
class Setting:
    name: str
    label: str
    type: SettingType
    value: SettingValue
    readonly: bool
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None


@dataclass(frozen=True)
class SettingGroup:
    name: str
    label: str
    settings: list[Setting]


@dataclass(frozen=True)
class CameraStatus:
    manufacturer: str
    model: str
    battery: str | None
    can_preview: bool
    liveview_active: bool
    liveview_blocked_reason: str | None


@dataclass(frozen=True)
class CapturedFile:
    name: str
    data: bytes


class CameraError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class CameraDisconnected(CameraError):
    """The connection is lost: the session drops it and reconnects on the next call."""


class Camera(Protocol):
    def status(self) -> CameraStatus: ...
    def settings(self) -> list[SettingGroup]: ...
    def set(self, name: str, value: SettingValue) -> Setting: ...
    def capture(self) -> list[CapturedFile]: ...
    def preview(self) -> bytes: ...
    def end_liveview(self) -> None: ...
    def close(self) -> None: ...


def liveview_block_reason(text: str | None) -> str | None:
    """Return the camera's explanation when its status text says live view is refused."""
    if text and text.startswith(LIVEVIEW_PROHIBIT_PREFIX):
        return text
    return None


def validate(setting: Setting | None, name: str, value: object, lang: str) -> SettingValue:
    """Check a value against the setting as currently reported; return it coerced."""
    if setting is None:
        raise CameraError(msg(lang, "unknown_setting", name=name), 404)
    if setting.readonly:
        raise CameraError(msg(lang, "readonly", name=name), 409)
    if setting.type in ("choice", "text"):
        if not isinstance(value, str):
            raise CameraError(msg(lang, "expected_text", name=name), 422)
        choices = setting.choices or []
        if setting.type == "choice" and value not in choices:
            allowed = ", ".join(choices)
            raise CameraError(
                msg(lang, "not_in_choices", name=name, value=value, allowed=allowed), 422
            )
        return value
    if setting.type == "range":
        return _validate_range(setting, value, lang)
    if setting.type == "toggle":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int) and value in (0, 1):
            return value
        raise CameraError(msg(lang, "expected_toggle", name=name), 422)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CameraError(msg(lang, "expected_date", name=name), 422)
    return value


def _validate_range(setting: Setting, value: object, lang: str) -> float:
    name = setting.name
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CameraError(msg(lang, "expected_number", name=name), 422)
    number = float(value)
    low, high, step = setting.min, setting.max, setting.step
    in_range = (low is None or number >= low) and (high is None or number <= high)
    on_step = True
    if step and low is not None:
        steps = (number - low) / step
        on_step = abs(steps - round(steps)) < 1e-6
    if not (in_range and on_step):
        raise CameraError(
            msg(
                lang,
                "out_of_range",
                name=name,
                value=_fmt(number),
                min=_fmt(low),
                max=_fmt(high),
                step=_fmt(step),
            ),
            422,
        )
    return number


def _fmt(number: float | None) -> str:
    return "-" if number is None else f"{number:g}"
