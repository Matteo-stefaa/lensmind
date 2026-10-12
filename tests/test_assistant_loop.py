from typing import Any

import pytest

from lensmind.assistant.loop import Assistant, AssistantError
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
