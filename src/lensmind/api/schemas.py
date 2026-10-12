"""JSON request and response models."""

from dataclasses import asdict
from typing import Annotated, Self
from urllib.parse import quote

from pydantic import BaseModel, StringConstraints

from lensmind.assistant.loop import Turn
from lensmind.assistant.tools import Proposal
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
    assistant: bool = False


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


class SessionOut(BaseModel):
    id: str


class MessageIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChangeOut(BaseModel):
    name: str
    label: str
    old: int | float | str
    new: int | float | str
    reason: str


class FailedOut(BaseModel):
    name: str
    detail: str


class ProposalOut(BaseModel):
    id: str
    summary: str
    state: str
    changes: list[ChangeOut]
    applied: list[str]
    failed: FailedOut | None = None

    @classmethod
    def from_model(cls, proposal: Proposal) -> Self:
        failed = proposal.failed
        return cls(
            id=proposal.id,
            summary=proposal.summary,
            state=proposal.state,
            changes=[ChangeOut(**asdict(change)) for change in proposal.changes],
            applied=[change.name for change in proposal.applied],
            failed=FailedOut(name=failed[0], detail=failed[1]) if failed else None,
        )


class TurnOut(BaseModel):
    reply: str
    proposal: ProposalOut | None = None
    question: str | None = None
    finished: bool
    limit_reached: bool

    @classmethod
    def from_turn(cls, turn: Turn) -> Self:
        return cls(
            reply=turn.reply,
            proposal=ProposalOut.from_model(turn.proposal) if turn.proposal else None,
            question=turn.question,
            finished=turn.finished,
            limit_reached=turn.limit_reached,
        )
