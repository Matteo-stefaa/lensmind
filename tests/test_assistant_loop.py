import base64
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from lensmind.assistant.loop import IMAGE_REMOVED, Assistant, AssistantError
from lensmind.assistant.prompts import system_prompt
from lensmind.assistant.provider import (
    FakeProvider,
    ModelReply,
    ProviderError,
    reply,
    text_block,
    tool_use_block,
)
from lensmind.camera.base import CameraError, Setting, SettingValue
from lensmind.camera.mock import MockCamera
from lensmind.storage import PhotoStore

PROPOSE_ISO = tool_use_block(
    "p1",
    "propose_settings",
    summary="Brighter",
    changes=[{"name": "iso", "value": "400", "reason": "Dim room"}],
)


def make(
    script: list[ModelReply | Exception],
    camera: MockCamera | None = None,
    max_turns: int = 6,
) -> tuple[Assistant, MockCamera, FakeProvider, str]:
    camera = camera or MockCamera(lang="en")
    provider = FakeProvider(script)
    assistant = Assistant(camera, provider, "en", max_turns)
    return assistant, camera, provider, assistant.start().id


def value_of(camera: MockCamera, name: str) -> object:
    return next(s.value for g in camera.settings() for s in g.settings if s.name == name)


def last_user_content(provider: FakeProvider) -> list[dict[str, Any]]:
    return provider.requests[-1][-1]["content"]


def test_system_prompt_names_the_language() -> None:
    assert "Italian" in system_prompt("it")
    assert "English" in system_prompt("en")


def test_reads_state_then_proposes_and_waits() -> None:
    assistant, camera, provider, cid = make(
        [
            reply(text_block("Reading."), tool_use_block("s1", "get_camera_state")),
            reply(text_block("Raise ISO."), PROPOSE_ISO),
        ]
    )
    turn = assistant.send(cid, "too dark")
    assert turn.reply == "Raise ISO."
    assert turn.proposal is not None
    assert [(c.name, c.new) for c in turn.proposal.changes] == [("iso", "400")]
    assert value_of(camera, "iso") == "100"
    result = last_user_content(provider)[0]
    assert result["tool_use_id"] == "s1"
    assert '"primary"' in result["content"]


def test_invalid_value_goes_back_to_the_model_with_allowed_values() -> None:
    bad = tool_use_block(
        "p0",
        "propose_settings",
        summary="x",
        changes=[{"name": "iso", "value": "500", "reason": "r"}],
    )
    assistant, _, provider, cid = make([reply(bad), reply(PROPOSE_ISO)])
    turn = assistant.send(cid, "too dark")
    assert turn.proposal is not None
    error = last_user_content(provider)[0]
    assert error["is_error"] is True
    assert "1600" in error["content"]


def test_nothing_is_applied_without_approval() -> None:
    assistant, camera, _, cid = make([reply(PROPOSE_ISO)])
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    assert value_of(camera, "iso") == "100"
    applied = assistant.apply(cid, proposal.id)
    assert applied.state == "applied"
    assert [c.name for c in applied.applied] == ["iso"]
    assert value_of(camera, "iso") == "400"
    with pytest.raises(AssistantError) as caught:
        assistant.apply(cid, proposal.id)
    assert caught.value.status == 409


def test_unknown_proposal_and_session() -> None:
    assistant, _, _, cid = make([])
    with pytest.raises(AssistantError) as caught:
        assistant.apply(cid, "nope")
    assert caught.value.status == 404
    with pytest.raises(AssistantError) as caught:
        assistant.send("nope", "hi")
    assert caught.value.status == 404


def test_new_message_supersedes_a_pending_proposal() -> None:
    assistant, _, provider, cid = make([reply(PROPOSE_ISO), reply(text_block("Leaving it."))])
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    assistant.send(cid, "no thanks")
    assert proposal.state == "superseded"
    first = last_user_content(provider)[0]
    assert first["tool_use_id"] == "p1"
    assert "Not applied" in first["content"]
    with pytest.raises(AssistantError) as caught:
        assistant.apply(cid, proposal.id)
    assert caught.value.status == 409


def test_apply_outcome_reaches_the_model_with_the_next_message() -> None:
    assistant, _, provider, cid = make([reply(PROPOSE_ISO), reply(text_block("Good."))])
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    assistant.apply(cid, proposal.id)
    assistant.send(cid, "thanks")
    content = last_user_content(provider)
    assert "Applied: iso=400" in content[0]["content"]
    assert content[-1] == text_block("thanks")


def test_change_invalid_at_apply_time_writes_nothing() -> None:
    propose = tool_use_block(
        "p1",
        "propose_settings",
        summary="Freeze motion",
        changes=[
            {"name": "iso", "value": "400", "reason": "r"},
            {"name": "shutterspeed2", "value": "1/60", "reason": "r"},
        ],
    )
    assistant, camera, _, cid = make([reply(propose)])
    proposal = assistant.send(cid, "sport").proposal
    assert proposal is not None
    camera.turn_dial("A")
    with pytest.raises(CameraError) as caught:
        assistant.apply(cid, proposal.id)
    assert caught.value.status == 409
    assert value_of(camera, "iso") == "100"
    assert proposal.state == "pending"


class FailingCamera(MockCamera):
    def set(self, name: str, value: SettingValue) -> Setting:
        if name == "burstnumber":
            raise CameraError("Camera busy", 503)
        return super().set(name, value)


def test_failure_midway_is_reported_as_partial() -> None:
    propose = tool_use_block(
        "p1",
        "propose_settings",
        summary="Burst",
        changes=[
            {"name": "iso", "value": "400", "reason": "r"},
            {"name": "burstnumber", "value": 3, "reason": "r"},
        ],
    )
    assistant, camera, _, cid = make([reply(propose)], camera=FailingCamera(lang="en"))
    proposal = assistant.send(cid, "burst").proposal
    assert proposal is not None
    result = assistant.apply(cid, proposal.id)
    assert result.state == "partial"
    assert [c.name for c in result.applied] == ["iso"]
    assert result.failed == ("burstnumber", "Camera busy")
    assert value_of(camera, "iso") == "400"


def test_ask_user_pauses_and_the_answer_becomes_the_tool_result() -> None:
    assistant, _, provider, cid = make(
        [
            reply(
                text_block("One thing first."),
                tool_use_block("q1", "ask_user", question="Turn the dial to M?"),
            ),
            reply(text_block("Thanks.")),
        ]
    )
    turn = assistant.send(cid, "portrait")
    assert turn.question == "Turn the dial to M?"
    assert turn.reply == "One thing first.\n\nTurn the dial to M?"
    assert len(provider.requests) == 1
    assistant.send(cid, "done")
    content = last_user_content(provider)
    assert content[0] == {"type": "tool_result", "tool_use_id": "q1", "content": "done"}


def test_finish_ends_the_turn_with_its_summary() -> None:
    assistant, _, provider, cid = make(
        [
            reply(text_block("Done."), tool_use_block("f1", "finish", summary="ISO is set.")),
            reply(text_block("Hello again.")),
        ]
    )
    turn = assistant.send(cid, "ok")
    assert turn.finished is True
    assert turn.reply == "Done.\n\nISO is set."
    assistant.send(cid, "hi")
    assert last_user_content(provider)[0]["tool_use_id"] == "f1"


def test_turn_limit_stops_and_reports() -> None:
    state = reply(tool_use_block("s1", "get_camera_state"))
    state2 = reply(tool_use_block("s2", "get_camera_state"))
    assistant, _, provider, cid = make([state, state2, reply(text_block("Go on."))], max_turns=2)
    turn = assistant.send(cid, "think hard")
    assert turn.limit_reached is True
    assert "2" in turn.reply
    assert len(provider.requests) == 2
    assistant.send(cid, "continue")
    assert last_user_content(provider)[0]["tool_use_id"] == "s2"


def test_provider_error_restores_the_conversation() -> None:
    assistant, _, provider, cid = make([ProviderError("down"), reply(text_block("Hi."))])
    with pytest.raises(AssistantError) as caught:
        assistant.send(cid, "hello")
    assert caught.value.status == 502
    assert "down" in caught.value.message
    assert assistant.get(cid).history == []
    assert assistant.send(cid, "hello").reply == "Hi."
    assert len(provider.requests[-1]) == 1


def test_provider_error_keeps_pending_proposal() -> None:
    assistant, camera, _, cid = make([reply(PROPOSE_ISO), ProviderError("down")])
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    with pytest.raises(AssistantError):
        assistant.send(cid, "and more contrast")
    assert proposal.state == "pending"
    assert proposal.reported is False
    assert assistant.apply(cid, proposal.id).state == "applied"
    assert value_of(camera, "iso") == "400"


def test_refusal_is_reported_as_incomplete() -> None:
    assistant, _, _, cid = make([ModelReply([text_block("")], "refusal")])
    with pytest.raises(AssistantError) as caught:
        assistant.send(cid, "hello")
    assert caught.value.status == 502
    assert "refusal" in caught.value.message
    assert assistant.get(cid).history == []


def test_camera_error_in_tool_is_reported_to_model() -> None:
    camera = MockCamera(lang="en")
    assistant, _, provider, cid = make(
        [reply(tool_use_block("s1", "get_camera_state")), reply(text_block("Camera gone."))],
        camera=camera,
    )
    camera.simulate_disconnect()
    turn = assistant.send(cid, "hello")
    assert turn.reply == "Camera gone."
    result = last_user_content(provider)[0]
    assert result["is_error"] is True
    assert "not connected" in result["content"]


def test_second_proposal_in_one_reply_is_rejected() -> None:
    other = tool_use_block(
        "p2",
        "propose_settings",
        summary="x",
        changes=[{"name": "iso", "value": "800", "reason": "r"}],
    )
    assistant, _, provider, cid = make([reply(PROPOSE_ISO, other), reply(text_block("OK."))])
    turn = assistant.send(cid, "too dark")
    assert turn.proposal is not None
    assert turn.proposal.tool_use_id == "p1"
    assistant.send(cid, "hm")
    ids = {b["tool_use_id"] for b in last_user_content(provider) if b["type"] == "tool_result"}
    assert ids == {"p1", "p2"}


def test_busy_conversation_rejects_send_and_apply() -> None:
    assistant, camera, _, cid = make([reply(PROPOSE_ISO)])
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    conversation = assistant.get(cid)
    conversation.lock.acquire()
    try:
        with pytest.raises(AssistantError) as caught:
            assistant.send(cid, "again")
        assert caught.value.status == 409
        with pytest.raises(AssistantError) as caught:
            assistant.apply(cid, proposal.id)
        assert caught.value.status == 409
    finally:
        conversation.lock.release()
    assert value_of(camera, "iso") == "100"


def test_oldest_conversation_is_evicted() -> None:
    assistant = Assistant(MockCamera(lang="en"), FakeProvider(), "en", 6, max_conversations=2)
    first = assistant.start().id
    assistant.start()
    assistant.start()
    with pytest.raises(AssistantError):
        assistant.get(first)


@pytest.mark.parametrize(
    "content", [[], [{"type": "thinking", "thinking": "", "signature": "sig"}]]
)
def test_empty_reply_is_reported_and_rolled_back(content: list[dict[str, Any]]) -> None:
    assistant, _, _, cid = make([ModelReply(content, "end_turn"), reply(text_block("Hi."))])
    with pytest.raises(AssistantError) as caught:
        assistant.send(cid, "hello")
    assert caught.value.status == 502
    assert assistant.get(cid).history == []
    assert assistant.send(cid, "hello").reply == "Hi."


# evaluate_shot ---------------------------------------------------------------

EVALUATE = tool_use_block("e1", "evaluate_shot")


def make_with_photos(
    script: list[ModelReply | Exception], root: Path, now: float = 1_000_000.0
) -> tuple[Assistant, MockCamera, FakeProvider, str, PhotoStore]:
    camera = MockCamera(lang="en")
    provider = FakeProvider(script)
    store = PhotoStore(root)
    assistant = Assistant(camera, provider, "en", 6, photos=store, clock=lambda: now)
    return assistant, camera, provider, assistant.start().id, store


def shoot(camera: MockCamera, store: PhotoStore, when: float) -> None:
    shot = store.save(camera.capture())
    for name in shot.files:
        os.utime(store.root / name, (when, when))


def evaluation(provider: FakeProvider, request: int = -1) -> tuple[dict[str, Any], Any]:
    result = provider.requests[request][-1]["content"][0]
    assert result["tool_use_id"] == "e1"
    text, image = result["content"]
    return json.loads(text["text"]), image


def test_evaluate_sends_a_small_image_with_stats(tmp_path: Path) -> None:
    assistant, camera, provider, cid, store = make_with_photos(
        [reply(EVALUATE), reply(text_block("Well exposed."))], tmp_path
    )
    shoot(camera, store, 999_990.0)
    turn = assistant.send(cid, "how is it?")
    assert turn.reply == "Well exposed."
    data, image = evaluation(provider)
    assert data["file"].endswith("DSC_0001.JPG")
    assert data["seconds_since_shot"] == 10
    assert data["taken_after_last_applied_proposal"] is None
    assert data["shooting_data"]["iso"] == 100
    assert 0 <= data["stats"]["clipped_highlights_percent"] <= 100
    assert image["type"] == "image"
    assert image["source"]["media_type"] == "image/jpeg"
    with Image.open(io.BytesIO(base64.b64decode(image["source"]["data"]))) as small:
        assert max(small.size) <= 1024


def test_evaluate_reports_overexposure(tmp_path: Path) -> None:
    assistant, camera, provider, cid, store = make_with_photos(
        [reply(EVALUATE), reply(text_block("Too bright."))], tmp_path
    )
    shoot(camera, store, 999_990.0)
    camera.set("iso", "3200")
    shoot(camera, store, 999_995.0)
    assistant.send(cid, "how is it?")
    data, _ = evaluation(provider)
    assert data["shooting_data"]["iso"] == 3200
    assert data["stats"]["clipped_highlights_percent"] > 50


def test_evaluate_tells_whether_the_shot_follows_the_applied_proposal(tmp_path: Path) -> None:
    clock = [1_000.0]
    camera = MockCamera(lang="en")
    provider = FakeProvider(
        [reply(PROPOSE_ISO), reply(EVALUATE), reply(text_block("Old shot.")), reply(EVALUATE)]
        + [reply(text_block("New shot."))]
    )
    store = PhotoStore(tmp_path)
    assistant = Assistant(camera, provider, "en", 6, photos=store, clock=lambda: clock[0])
    cid = assistant.start().id
    shoot(camera, store, 900.0)
    proposal = assistant.send(cid, "too dark").proposal
    assert proposal is not None
    assistant.apply(cid, proposal.id)
    assistant.send(cid, "look")
    assert evaluation(provider)[0]["taken_after_last_applied_proposal"] is False
    shoot(camera, store, 1_100.0)
    clock[0] = 1_200.0
    assistant.send(cid, "and now?")
    assert evaluation(provider)[0]["taken_after_last_applied_proposal"] is True


def test_evaluate_without_a_shot_asks_for_one(tmp_path: Path) -> None:
    assistant, _, provider, cid, _ = make_with_photos(
        [reply(EVALUATE), reply(text_block("Take a shot."))], tmp_path
    )
    assistant.send(cid, "look")
    result = last_user_content(provider)[0]
    assert result["is_error"] is True
    assert "shutter button" in result["content"]


def test_evaluate_without_a_photo_source_is_an_error() -> None:
    assistant, _, provider, cid = make([reply(EVALUATE), reply(text_block("No."))])
    assistant.send(cid, "look")
    assert last_user_content(provider)[0]["is_error"] is True


def test_evaluate_raw_only_shot_suggests_a_jpeg(tmp_path: Path) -> None:
    assistant, camera, provider, cid, store = make_with_photos(
        [reply(EVALUATE), reply(text_block("Need a JPEG."))], tmp_path
    )
    camera.set("imagequality", "NEF (Raw)")
    shoot(camera, store, 999_990.0)
    assistant.send(cid, "look")
    result = last_user_content(provider)[0]
    assert result["is_error"] is True
    assert "JPEG" in result["content"]


def test_only_the_newest_images_stay_in_the_history(tmp_path: Path) -> None:
    script: list[ModelReply | Exception] = []
    for _ in range(3):
        script += [reply(EVALUATE), reply(text_block("Seen."))]
    assistant, camera, provider, cid, store = make_with_photos(script, tmp_path)
    for number in range(3):
        shoot(camera, store, 999_000.0 + number)
        assistant.send(cid, f"shot {number}")
    history = provider.requests[-1]
    results = [
        block
        for message in history
        if message["role"] == "user"
        for block in message["content"]
        if block.get("type") == "tool_result" and isinstance(block.get("content"), list)
    ]
    kinds = [result["content"][1]["type"] for result in results]
    assert kinds == ["text", "image", "image"]
    assert results[0]["content"][1]["text"] == IMAGE_REMOVED
