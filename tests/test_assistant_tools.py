import json
from typing import Any

import pytest

from lensmind.assistant.tools import (
    TOOLS,
    ProposalRejected,
    build_proposal,
    camera_state,
    check_changes,
)
from lensmind.camera.base import CameraError
from lensmind.camera.mock import MockCamera


@pytest.fixture
def camera() -> MockCamera:
    return MockCamera(lang="en")


def value_of(camera: MockCamera, name: str) -> object:
    return next(s.value for g in camera.settings() for s in g.settings if s.name == name)


def propose(camera: MockCamera, *changes: dict[str, Any]) -> Any:
    return build_proposal(camera, {"summary": "Test", "changes": list(changes)}, "call-1")


def test_tool_names() -> None:
    assert [tool["name"] for tool in TOOLS] == [
        "get_camera_state",
        "propose_settings",
        "ask_user",
        "evaluate_shot",
        "finish",
    ]
    for tool in TOOLS:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"


def test_state_has_primary_roles_with_allowed_values(camera: MockCamera) -> None:
    state = camera_state(camera)
    assert state["camera"] == {"model": "Nikon Corporation D3500", "battery": "20%"}
    assert state["primary"]["iso"]["value"] == "100"
    assert "1600" in state["primary"]["iso"]["choices"]
    assert state["primary"]["mode"]["readonly"] is True
    assert "burstnumber" in state["writable"]
    assert "expprogram" not in state["writable"]
    json.dumps(state)


def test_state_by_name(camera: MockCamera) -> None:
    state = camera_state(camera, ["burstnumber", "nope"])
    burst = state["settings"]["burstnumber"]
    assert (burst["type"], burst["min"], burst["max"], burst["step"]) == ("range", 1.0, 100.0, 1.0)
    assert "choices" not in burst
    assert state["unknown"] == ["nope"]


def test_valid_proposal_changes_nothing(camera: MockCamera) -> None:
    proposal = propose(
        camera,
        {"name": "iso", "value": "400", "reason": "Dim room"},
        {"name": "burstnumber", "value": 3, "reason": "Three frames"},
    )
    assert proposal.state == "pending"
    assert proposal.tool_use_id == "call-1"
    assert proposal.summary == "Test"
    assert [(c.name, c.label, c.old, c.new, c.reason) for c in proposal.changes] == [
        ("iso", "ISO Speed", "100", "400", "Dim room"),
        ("burstnumber", "Burst Number", 1.0, 3.0, "Three frames"),
    ]
    assert value_of(camera, "iso") == "100"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"name": "nope", "value": "1", "reason": "r"}, "Unknown setting: nope"),
        ({"name": "expprogram", "value": "A", "reason": "r"}, "expprogram cannot be changed"),
        ({"name": "iso", "value": "123", "reason": "r"}, "Allowed values: 100, 200"),
        ({"name": "burstnumber", "value": 500, "reason": "r"}, "Allowed from 1 to 100"),
        ({"name": "iso", "value": "100", "reason": "r"}, "iso is already 100"),
        ({"name": "iso", "value": "400", "reason": "  "}, "iso: reason is missing"),
        ({"value": "400"}, "change 1: needs name, value and reason"),
    ],
)
def test_invalid_change_is_rejected(
    camera: MockCamera, change: dict[str, Any], fragment: str
) -> None:
    with pytest.raises(ProposalRejected) as caught:
        propose(camera, change)
    assert fragment in str(caught.value)


def test_number_for_choice_lists_allowed_values(camera: MockCamera) -> None:
    with pytest.raises(ProposalRejected) as caught:
        propose(camera, {"name": "iso", "value": 400, "reason": "r"})
    assert "iso takes one of these values, as text: 100, 200, 400" in str(caught.value)


def test_duplicates_and_empty_lists_are_rejected(camera: MockCamera) -> None:
    with pytest.raises(ProposalRejected, match="iso: proposed more than once"):
        propose(
            camera,
            {"name": "iso", "value": "400", "reason": "a"},
            {"name": "iso", "value": "800", "reason": "b"},
        )
    with pytest.raises(ProposalRejected, match="changes must be a non-empty list"):
        build_proposal(camera, {"summary": "x", "changes": []}, "c")
    with pytest.raises(ProposalRejected, match="summary must be a non-empty string"):
        build_proposal(camera, {"changes": [{"name": "iso", "value": "400", "reason": "r"}]}, "c")


def test_all_errors_are_reported_together(camera: MockCamera) -> None:
    with pytest.raises(ProposalRejected) as caught:
        propose(
            camera,
            {"name": "nope", "value": "1", "reason": "r"},
            {"name": "iso", "value": "123", "reason": "r"},
        )
    assert len(caught.value.errors) == 2


def test_check_changes_after_the_dial_moves(camera: MockCamera) -> None:
    proposal = propose(camera, {"name": "shutterspeed2", "value": "1/60", "reason": "r"})
    check_changes(camera, proposal.changes, "en")
    camera.turn_dial("A")
    with pytest.raises(CameraError) as caught:
        check_changes(camera, proposal.changes, "en")
    assert caught.value.status == 409
