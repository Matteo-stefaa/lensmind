"""Tools the model can call, and their execution against the camera."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from lensmind.camera.base import Camera, CameraError, Setting, SettingGroup, SettingValue, validate
from lensmind.camera.primary import resolve_primary

ProposalState = Literal["pending", "applied", "partial", "failed", "superseded"]

# Tool errors are read by the model: always English, whatever the user's language.
MODEL_LANGUAGE = "en"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_camera_state",
        "description": (
            "Read the camera. Without arguments: the main settings (shutter, aperture, ISO, "
            "exposure compensation, white balance, focus, quality, mode) with their current "
            "value and allowed values, the camera model and battery, and the names of every "
            "writable setting. With `names`: the same detail for those settings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Setting names to read in detail.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "propose_settings",
        "description": (
            "Propose setting changes to the user, who approves or declines them as a whole. "
            "Nothing changes until the user approves. Use only values reported as allowed by "
            "get_camera_state. One proposal per reply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One sentence: what the proposal achieves.",
                },
                "changes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": ["string", "number", "integer", "boolean"]},
                            "reason": {
                                "type": "string",
                                "description": "Why, in words the user understands.",
                            },
                        },
                        "required": ["name", "value", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "changes"],
            "additionalProperties": False,
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Ask the user for something only they can do or know: turning the mode dial, "
            "zooming, moving, framing, using the flash. Waits for the user's reply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "evaluate_shot",
        "description": (
            "Look at the latest shot the user took: a reduced copy of the image, exposure "
            "statistics computed from it (luminance, clipped highlights and shadows, colour "
            "balance) and the shooting data recorded by the camera. Also says whether the "
            "shot was taken after the last approved proposal was applied. Prefer the "
            "statistics to your own impression for exposure."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "finish",
        "description": "End your work on the current request with a short summary for the user.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class Change:
    name: str
    label: str
    old: SettingValue
    new: SettingValue
    reason: str


@dataclass
class Proposal:
    id: str
    tool_use_id: str
    summary: str
    changes: list[Change]
    state: ProposalState = "pending"
    applied: list[Change] = field(default_factory=list)
    failed: tuple[str, str] | None = None
    reported: bool = False


class ProposalRejected(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def describe(setting: Setting) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": setting.name,
        "label": setting.label,
        "type": setting.type,
        "value": setting.value,
        "readonly": setting.readonly,
    }
    if setting.choices is not None:
        data["choices"] = setting.choices
    for key in ("min", "max", "step"):
        if getattr(setting, key) is not None:
            data[key] = getattr(setting, key)
    return data


def _index(groups: list[SettingGroup]) -> dict[str, Setting]:
    settings: dict[str, Setting] = {}
    for group in groups:
        for setting in group.settings:
            settings.setdefault(setting.name, setting)
    return settings


def camera_state(camera: Camera, names: list[str] | None = None) -> dict[str, Any]:
    groups = camera.settings()
    settings = _index(groups)
    if names:
        return {
            "settings": {name: describe(settings[name]) for name in names if name in settings},
            "unknown": [name for name in names if name not in settings],
        }
    status = camera.status()
    return {
        "camera": {
            "model": f"{status.manufacturer} {status.model}".strip(),
            "battery": status.battery,
        },
        "primary": {
            role: describe(settings[name]) for role, name in resolve_primary(groups).items()
        },
        "writable": sorted(name for name, setting in settings.items() if not setting.readonly),
    }


def build_proposal(camera: Camera, data: dict[str, Any], tool_use_id: str) -> Proposal:
    """Validate a `propose_settings` call against the camera as it is now."""
    summary = data.get("summary")
    changes = data.get("changes")
    errors: list[str] = []
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary must be a non-empty string")
    if not isinstance(changes, list) or not changes:
        raise ProposalRejected([*errors, "changes must be a non-empty list"])
    settings = _index(camera.settings())
    accepted: list[Change] = []
    seen: set[str] = set()
    for position, item in enumerate(changes, 1):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            errors.append(f"change {position}: needs name, value and reason")
            continue
        name, raw, reason = item["name"], item.get("value"), item.get("reason")
        if name in seen:
            errors.append(f"{name}: proposed more than once")
            continue
        seen.add(name)
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{name}: reason is missing")
            continue
        setting = settings.get(name)
        if setting is not None and setting.type == "choice" and not isinstance(raw, str):
            allowed = ", ".join(setting.choices or [])
            errors.append(f"{name} takes one of these values, as text: {allowed}")
            continue
        try:
            value = validate(setting, name, raw, MODEL_LANGUAGE)
        except CameraError as error:
            errors.append(error.message)
            continue
        assert setting is not None  # validate() rejects unknown names
        if value == setting.value:
            errors.append(f"{name} is already {setting.value}")
            continue
        accepted.append(Change(name, setting.label, setting.value, value, reason.strip()))
    if errors or not isinstance(summary, str):
        raise ProposalRejected(errors)
    return Proposal(
        id=uuid.uuid4().hex[:12],
        tool_use_id=tool_use_id,
        summary=summary.strip(),
        changes=accepted,
    )


def check_changes(camera: Camera, changes: list[Change], lang: str) -> None:
    """Raise the first CameraError if a change is no longer valid for the camera."""
    settings = _index(camera.settings())
    for change in changes:
        validate(settings.get(change.name), change.name, change.new, lang)
