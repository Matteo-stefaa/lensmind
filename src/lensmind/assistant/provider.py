"""The model behind the assistant: the Provider protocol, Claude, and a scripted fake.

This is the only module that imports the AI SDK.
"""

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

Block = dict[str, Any]

MAX_TOKENS = 16000
# Seconds before a request is abandoned. The Pi reaches the API through a phone
# hotspot: a stalled connection must not hold the conversation for the SDK's
# default ten minutes per attempt.
REQUEST_TIMEOUT = 120.0


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ModelReply:
    """One model response. `content` is kept verbatim, thinking blocks included: the API
    needs them back unchanged in later requests."""

    content: list[Block]
    stop_reason: str

    @property
    def text(self) -> str:
        parts = (b.get("text", "").strip() for b in self.content if b.get("type") == "text")
        return "\n\n".join(part for part in parts if part)

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [
            ToolCall(b["id"], b["name"], dict(b.get("input") or {}))
            for b in self.content
            if b.get("type") == "tool_use"
        ]


class ProviderError(Exception):
    """The model could not be reached or did not answer."""


class Provider(Protocol):
    def complete(self, system: str, messages: list[Block], tools: list[Block]) -> ModelReply: ...


class ClaudeProvider:
    def __init__(self, api_key: str, model: str, client: Any = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=1)
        self._client = client
        self._model = model

    def complete(self, system: str, messages: list[Block], tools: list[Block]) -> ModelReply:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                # Tools render before the system prompt: this breakpoint caches both.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tools,
                messages=messages,
            )
        except Exception as error:  # network, authentication, rate limit, bad request
            raise ProviderError(str(error) or type(error).__name__) from error
        return ModelReply(
            content=[block.to_dict() for block in response.content],
            stop_reason=str(response.stop_reason),
        )


# Test support ----------------------------------------------------------------


def text_block(text: str) -> Block:
    return {"type": "text", "text": text}


def tool_use_block(call_id: str, name: str, **input: Any) -> Block:
    return {"type": "tool_use", "id": call_id, "name": name, "input": input}


def reply(*blocks: Block) -> ModelReply:
    """A reply as the model sends it: stop reason `tool_use` when it calls a tool."""
    calls = any(block["type"] == "tool_use" for block in blocks)
    return ModelReply(list(blocks), "tool_use" if calls else "end_turn")


def check_history(messages: list[Block]) -> None:
    """Raise AssertionError unless the Messages API would accept `messages`."""
    assert messages, "history is empty"
    assert messages[-1]["role"] == "user", "history must end with a user message"
    for index, message in enumerate(messages):
        expected = "user" if index % 2 == 0 else "assistant"
        assert message["role"] == expected, f"message {index} should be {expected}"
        content = message["content"]
        assert isinstance(content, list) and content, f"message {index} has no content"
        if expected == "assistant":
            continue
        previous = messages[index - 1]["content"] if index else []
        calls = [b["id"] for b in previous if b.get("type") == "tool_use"]
        results = [b["tool_use_id"] for b in content if b.get("type") == "tool_result"]
        leading = [b.get("type") for b in content[: len(results)]]
        assert leading == ["tool_result"] * len(results), (
            f"message {index}: tool results must come first"
        )
        assert sorted(results) == sorted(calls), (
            f"message {index}: results {results} do not answer calls {calls}"
        )


class FakeProvider:
    """Scripted provider for tests: returns (or raises) the scripted items in order and
    checks the history of every request."""

    def __init__(self, script: Iterable[ModelReply | Exception] = ()) -> None:
        self.script = list(script)
        self.requests: list[list[Block]] = []
        self.system: str | None = None
        self.tools: list[Block] = []

    def complete(self, system: str, messages: list[Block], tools: list[Block]) -> ModelReply:
        check_history(messages)
        self.system, self.tools = system, tools
        self.requests.append(copy.deepcopy(messages))
        if not self.script:
            raise AssertionError("FakeProvider has no scripted reply left")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
