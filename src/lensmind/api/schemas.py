"""JSON request and response models."""

from dataclasses import asdict
from typing import Self
from urllib.parse import quote

from pydantic import BaseModel

from lensmind.camera.base import CameraStatus, Setting, SettingGroup
from lensmind.storage import Shot


class SettingOut(BaseModel):
    name: str
    label: str
    type: str
    value: int | float | str
    readonly: bool
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None

    @classmethod
    def from_model(cls, setting: Setting) -> Self:
        return cls(**asdict(setting))


class GroupOut(BaseModel):
    name: str
    label: str
    settings: list[SettingOut]

    @classmethod
    def from_model(cls, group: SettingGroup) -> Self:
        return cls(
            name=group.name,
            label=group.label,
            settings=[SettingOut.from_model(s) for s in group.settings],
        )


class SettingsOut(BaseModel):
    groups: list[GroupOut]
    primary: dict[str, str]


class SetValueIn(BaseModel):
    value: bool | int | float | str


class CameraStatusOut(BaseModel):
    manufacturer: str
    model: str
    battery: str | None
    can_preview: bool
    liveview_active: bool
    liveview_blocked_reason: str | None

    @classmethod
    def from_model(cls, status: CameraStatus) -> Self:
        return cls(**asdict(status))


class StatusOut(BaseModel):
    connected: bool
    detail: str | None = None
    language: str
    camera: CameraStatusOut | None = None


class FileOut(BaseModel):
    name: str
    url: str


class ShotOut(BaseModel):
    id: str
    files: list[FileOut]
    thumb_url: str | None

    @classmethod
    def from_shot(cls, shot: Shot) -> Self:
        return cls(
            id=shot.id,
            files=[FileOut(name=n, url=f"/api/photos/{quote(n)}") for n in shot.files],
            thumb_url=f"/api/photos/{quote(shot.thumb)}/thumb" if shot.thumb else None,
        )
