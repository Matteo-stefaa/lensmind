from types import SimpleNamespace
from typing import Any

import pytest

from lensmind.assistant.provider import (
    REQUEST_TIMEOUT,
    ClaudeProvider,
    FakeProvider,
    ModelReply,
    ProviderError,
    ToolCall,
    check_history,
    reply,
    text_block,
    tool_use_block,
)


class FakeBlock:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)


class FakeMessages:
    def __init__(self, outcome: list[dict[str, Any]] | Exception) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(content=[FakeBlock(b) for b in self.outcome], stop_reason="tool_use")


def test_reply_text_and_tool_calls() -> None:
    model_reply = ModelReply(
        [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            text_block("First."),
            tool_use_block("c1", "get_camera_state", names=["iso"]),
            text_block("  "),
        ],
        "tool_use",
    )
    assert model_reply.text == "First."
    assert model_reply.tool_calls == [ToolCall("c1", "get_camera_state", {"names": ["iso"]})]


def test_reply_builder_sets_stop_reason() -> None:
    assert reply(text_block("hi")).stop_reason == "end_turn"
    assert reply(tool_use_block("c1", "finish", summary="x")).stop_reason == "tool_use"


def test_claude_provider_sends_request_and_keeps_content_verbatim() -> None:
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    messages = FakeMessages([thinking, text_block("Hello")])
    provider = ClaudeProvider("key", "the-model", client=SimpleNamespace(messages=messages))
    history = [{"role": "user", "content": [text_block("hi")]}]
    tools = [{"name": "finish", "input_schema": {"type": "object"}}]

    result = provider.complete("be helpful", history, tools)

    assert result.content == [thinking, text_block("Hello")]
    assert result.stop_reason == "tool_use"
    call = messages.calls[0]
    assert call["model"] == "the-model"
    assert call["max_tokens"] == 16000
    assert call["system"] == [
        {"type": "text", "text": "be helpful", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["tools"] == tools
    assert call["messages"] == history


def test_claude_provider_wraps_errors() -> None:
    messages = FakeMessages(RuntimeError("connection refused"))
    provider = ClaudeProvider("key", "the-model", client=SimpleNamespace(messages=messages))
    with pytest.raises(ProviderError, match="connection refused"):
        provider.complete("s", [{"role": "user", "content": [text_block("hi")]}], [])


def test_valid_history_passes() -> None:
    check_history(
        [
            {"role": "user", "content": [text_block("hi")]},
            {"role": "assistant", "content": [tool_use_block("c1", "get_camera_state")]},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": "{}"},
                    text_block("go on"),
                ],
            },
        ]
    )


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "assistant", "content": [text_block("hi")]}],
        [
            {"role": "user", "content": [text_block("a")]},
            {"role": "user", "content": [text_block("b")]},
        ],
        [
            {"role": "user", "content": [text_block("hi")]},
            {"role": "assistant", "content": [tool_use_block("c1", "get_camera_state")]},
            {"role": "user", "content": [text_block("no result")]},
        ],
        [
            {"role": "user", "content": [text_block("hi")]},
            {"role": "assistant", "content": [tool_use_block("c1", "get_camera_state")]},
            {
                "role": "user",
                "content": [
                    text_block("text first"),
                    {"type": "tool_result", "tool_use_id": "c1", "content": "{}"},
                ],
            },
        ],
    ],
)
def test_invalid_history_fails(messages: list[dict[str, Any]]) -> None:
    with pytest.raises(AssertionError):
        check_history(messages)


def test_fake_provider_replays_script_and_records_requests() -> None:
    provider = FakeProvider([reply(text_block("one")), ProviderError("down")])
    history = [{"role": "user", "content": [text_block("hi")]}]
    assert provider.complete("sys", history, []).text == "one"
    with pytest.raises(ProviderError):
        provider.complete("sys", history, [])
    with pytest.raises(AssertionError, match="no scripted reply"):
        provider.complete("sys", history, [])
    assert provider.requests == [history, history, history]
    assert provider.system == "sys"


def test_claude_provider_bounds_how_long_a_request_can_hang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic

    created: dict[str, Any] = {}

    def fake_client(**kwargs: Any) -> SimpleNamespace:
        created.update(kwargs)
        return SimpleNamespace(messages=None)

    monkeypatch.setattr(anthropic, "Anthropic", fake_client)
    ClaudeProvider("key", "the-model")
    assert created == {"api_key": "key", "timeout": REQUEST_TIMEOUT, "max_retries": 1}
    assert REQUEST_TIMEOUT <= 120
