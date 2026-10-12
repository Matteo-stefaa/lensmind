# Phase 2 — Assistant by words: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A text request in the web app produces a validated proposal of camera settings, one reason per change, applied only after the user presses Apply.

**Architecture:** New package `src/lensmind/assistant/` (provider → tools → prompts → loop) talks to the camera only through the `Camera` protocol and to the model only through the `Provider` protocol. `api/routes_assistant.py` exposes sessions, messages and apply; the web app gets a conversation panel on the main screen. Conversations live in memory.

**Tech Stack:** Python 3.11, FastAPI, pydantic, `anthropic` SDK (imported only in `assistant/provider.py`), plain ES modules in `web/`, pytest, Node for pure web-logic tests.

**Spec:** `docs/superpowers/specs/2026-10-12-phase2-assistant-words-design.md`

## Global Constraints

- Dependencies point one way: `api → assistant → camera`. `assistant/` never imports FastAPI; `camera/` never imports `assistant/`.
- Only `assistant/provider.py` imports `anthropic`, and only inside `ClaudeProvider.__init__`.
- No model identifier anywhere in code: the model comes from `LENSMIND_MODEL`, the key from `ANTHROPIC_API_KEY`.
- Nothing is written to the camera before `POST .../proposals/{pid}/apply`.
- Hard limit in code: `LENSMIND_MAX_TURNS` (default 6) model calls per user message.
- Tests never call a real AI API or real hardware: `FakeProvider` + `MockCamera` only.
- User-facing strings in Italian and English, one table per layer (`assistant/prompts.py`, `api/messages.py`, `web/js/i18n.js`). Texts for the model are in English.
- Web: DOM through `el()`/`textContent` only, no `innerHTML`, no CDN, phone first.
- Style: type hints everywhere, `ruff check . && ruff format .` clean, line length 100.
- Commit messages: imperative sentence, no prefix, ending with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run Python through the project venv: `.venv/bin/python -m pytest`, `.venv/bin/ruff`.

## Review Focus

1. The server restarts mid-conversation: the next send gets 404; the web app must start a new session and resend once, not show an error. Pinned in Task 6 (`sendMessage` Node test).
2. A send fails (provider down, 502): the server rolls back, so the pending proposal must stay applicable on both sides. Pinned in Task 4 (`test_provider_error_keeps_pending_proposal`) and Task 6 (the card is re-rendered only after a successful send).
3. The model sends a number for a choice setting (`"iso": 400`): the tool error must list the allowed values as text, not just say "needs a text value". Pinned in Task 3 (`test_number_for_choice_lists_allowed_values`).
4. The camera disconnects while the model reads it: the tool returns an error result and the turn continues, no 500. Pinned in Task 4 (`test_camera_error_in_tool_is_reported_to_model`).
5. The user taps Apply while a message is still being processed: 409 busy, nothing written. Pinned in Task 4 (`test_busy_conversation_rejects_send_and_apply`).

---

## File map

| File | Responsibility |
|---|---|
| `src/lensmind/settings.py` (modify) | `anthropic_api_key`, `model`, `max_turns`, `assistant_ready` |
| `src/lensmind/assistant/__init__.py` (create) | package docstring |
| `src/lensmind/assistant/provider.py` (create) | `ModelReply`, `ToolCall`, `ProviderError`, `Provider`, `ClaudeProvider`, `FakeProvider`, `check_history`, block builders |
| `src/lensmind/assistant/tools.py` (create) | `TOOLS` schemas, `camera_state`, `Change`, `Proposal`, `ProposalRejected`, `build_proposal`, `check_changes` |
| `src/lensmind/assistant/prompts.py` (create) | system prompt, user-facing strings, `proposal_outcome` |
| `src/lensmind/assistant/loop.py` (create) | `Assistant`, `Conversation`, `Turn`, `AssistantError`, model loop, apply |
| `src/lensmind/api/schemas.py` (modify) | `MessageIn`, `SessionOut`, `ChangeOut`, `FailedOut`, `ProposalOut`, `TurnOut`, `StatusOut.assistant` |
| `src/lensmind/api/routes_assistant.py` (create) | three assistant endpoints |
| `src/lensmind/api/messages.py` (modify) | `assistant_not_configured` |
| `src/lensmind/api/app.py` (modify) | provider wiring, `AssistantError` handler, router |
| `src/lensmind/api/routes_camera.py` (modify) | `assistant` flag in `/api/status` |
| `web/js/chat_logic.js` (create) | pure: `cardState`, `changeLine`, `formatValue`, `sendMessage` |
| `web/js/assistant.js` (create) | conversation panel |
| `web/js/api.js`, `web/js/app.js`, `web/js/i18n.js`, `web/index.html`, `web/style.css` (modify) | wiring, strings, layout |
| `deploy/install.sh`, `pyproject.toml`, `README.md`, `CLAUDE.md` (modify) | dependency, env template, docs |
| `tests/test_settings.py`, `tests/test_deploy.py`, `tests/test_web_logic.py`, `tests/test_web_static.py` (modify) | |
| `tests/test_provider.py`, `tests/test_assistant_tools.py`, `tests/test_assistant_loop.py`, `tests/test_api_assistant.py` (create) | |

---

### Task 1: Assistant configuration, dependency and install template

**Files:**
- Modify: `src/lensmind/settings.py`
- Modify: `pyproject.toml`
- Modify: `deploy/install.sh:23-28`
- Modify: `README.md` (configuration table)
- Test: `tests/test_settings.py`, `tests/test_deploy.py`

**Interfaces:**
- Produces: `Settings.anthropic_api_key: str | None` (not in `repr`), `Settings.model: str | None`, `Settings.max_turns: int`, `Settings.assistant_ready -> bool`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings.py`, extend `test_defaults` with three asserts at the end:

```python
    assert settings.anthropic_api_key is None
    assert settings.model is None
    assert settings.max_turns == 6
```

Add `{"LENSMIND_MAX_TURNS": "0"}` to the `test_rejects_invalid_values` parametrize list, and append:

```python
def test_assistant_configuration() -> None:
    settings = Settings.from_env(
        {"ANTHROPIC_API_KEY": "sk-test", "LENSMIND_MODEL": "some-model", "LENSMIND_MAX_TURNS": "4"}
    )
    assert settings.anthropic_api_key == "sk-test"
    assert settings.model == "some-model"
    assert settings.max_turns == 4
    assert settings.assistant_ready is True


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"ANTHROPIC_API_KEY": "sk-test"},
        {"LENSMIND_MODEL": "some-model"},
        {"ANTHROPIC_API_KEY": "  ", "LENSMIND_MODEL": "some-model"},
    ],
)
def test_assistant_needs_key_and_model(env: dict[str, str]) -> None:
    assert Settings.from_env(env).assistant_ready is False


def test_api_key_is_not_in_repr() -> None:
    assert "sk-secret" not in repr(Settings.from_env({"ANTHROPIC_API_KEY": "sk-secret"}))
```

In `tests/test_deploy.py`, add to the `needed` list of `test_install_script_covers_the_documented_steps`:

```python
        "# ANTHROPIC_API_KEY=",
        "# LENSMIND_MODEL=",
        "chmod 600 /etc/lensmind.env",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_settings.py tests/test_deploy.py -q`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'anthropic_api_key'`, missing strings in install.sh).

- [ ] **Step 3: Implement**

`src/lensmind/settings.py` — add fields after `liveview_idle_seconds`, a property, and parsing:

```python
    liveview_idle_seconds: float = 5.0
    anthropic_api_key: str | None = field(default=None, repr=False)
    model: str | None = None
    max_turns: int = 6

    @property
    def assistant_ready(self) -> bool:
        """The assistant runs only with both an API key and a model identifier."""
        return bool(self.anthropic_api_key and self.model)
```

In `from_env`, before `photos_dir = ...`:

```python
        max_turns = int(env.get("LENSMIND_MAX_TURNS", "6"))
        if max_turns < 1:
            raise ValueError(f"LENSMIND_MAX_TURNS must be at least 1, not {max_turns}")
```

and add to the `cls(...)` call:

```python
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", "").strip() or None,
            model=env.get("LENSMIND_MODEL", "").strip() or None,
            max_turns=max_turns,
```

`pyproject.toml`:

```toml
dependencies = ["fastapi>=0.110", "uvicorn>=0.29", "Pillow>=10.0", "anthropic>=0.100"]
```

`deploy/install.sh` — replace the env block:

```bash
if [[ ! -f /etc/lensmind.env ]]; then
  cat > /etc/lensmind.env <<'ENV'
LENSMIND_PORT=80
LENSMIND_LANGUAGE=it
# Assistant: set both, then run: sudo systemctl restart lensmind
# ANTHROPIC_API_KEY=
# LENSMIND_MODEL=
ENV
fi
# It holds the API key: root only (systemd reads it before starting the service user).
chmod 600 /etc/lensmind.env
```

`README.md` — in the configuration table, after the `LENSMIND_MAX_TEST_SHOTS` row:

```markdown
| `LENSMIND_MAX_TURNS` | `6` | Model calls allowed per message to the assistant |
```

Install the new dependency: `.venv/bin/pip install -e ".[dev]"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/lensmind/settings.py pyproject.toml deploy/install.sh README.md tests/test_settings.py tests/test_deploy.py
git commit -m "Add assistant configuration and the anthropic dependency

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Provider protocol, Claude implementation, scripted fake

**Files:**
- Create: `src/lensmind/assistant/__init__.py`
- Create: `src/lensmind/assistant/provider.py`
- Test: `tests/test_provider.py`

**Interfaces:**
- Produces:
  - `Block = dict[str, Any]`
  - `ToolCall(id: str, name: str, input: dict[str, Any])` (frozen dataclass)
  - `ModelReply(content: list[Block], stop_reason: str)` with properties `text -> str`, `tool_calls -> list[ToolCall]`
  - `ProviderError(Exception)`
  - `Provider` protocol: `complete(system: str, messages: list[Block], tools: list[Block]) -> ModelReply`
  - `ClaudeProvider(api_key: str, model: str, client: Any = None)`
  - `FakeProvider(script: Iterable[ModelReply | Exception] = ())` with `.script`, `.requests: list[list[Block]]`, `.system`, `.tools`
  - `check_history(messages: list[Block]) -> None` (raises `AssertionError`)
  - `text_block(text) -> Block`, `tool_use_block(call_id, name, **input) -> Block`, `reply(*blocks) -> ModelReply`

- [ ] **Step 1: Write the failing tests** — `tests/test_provider.py`

```python
from types import SimpleNamespace
from typing import Any

import pytest

from lensmind.assistant.provider import (
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
        return SimpleNamespace(
            content=[FakeBlock(b) for b in self.outcome], stop_reason="tool_use"
        )


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_provider.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lensmind.assistant'`.

- [ ] **Step 3: Implement**

`src/lensmind/assistant/__init__.py`:

```python
"""The assistant: model provider, camera tools, conversation loop."""
```

`src/lensmind/assistant/provider.py`:

```python
"""The model behind the assistant: the Provider protocol, Claude, and a scripted fake.

This is the only module that imports the AI SDK.
"""

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

Block = dict[str, Any]

MAX_TOKENS = 16000


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

            client = anthropic.Anthropic(api_key=api_key)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_provider.py -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lensmind/assistant tests/test_provider.py
git commit -m "Add the assistant provider protocol, Claude provider and scripted fake

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Camera tools and proposal validation

**Files:**
- Create: `src/lensmind/assistant/tools.py`
- Test: `tests/test_assistant_tools.py`

**Interfaces:**
- Consumes: `Camera`, `CameraError`, `Setting`, `SettingGroup`, `SettingValue`, `validate(setting, name, value, lang)` from `lensmind.camera.base`; `resolve_primary(groups) -> dict[str, str]` from `lensmind.camera.primary`.
- Produces:
  - `TOOLS: list[dict[str, Any]]` — names in order `get_camera_state`, `propose_settings`, `ask_user`, `finish`
  - `describe(setting: Setting) -> dict[str, Any]`
  - `camera_state(camera: Camera, names: list[str] | None = None) -> dict[str, Any]`
  - `Change(name, label, old, new, reason)` (frozen dataclass)
  - `Proposal(id, tool_use_id, summary, changes, state="pending", applied=[], failed=None, reported=False)`; `ProposalState = Literal["pending", "applied", "partial", "failed", "superseded"]`
  - `ProposalRejected(errors: list[str])` with `.errors`
  - `build_proposal(camera: Camera, data: dict[str, Any], tool_use_id: str) -> Proposal`
  - `check_changes(camera: Camera, changes: list[Change], lang: str) -> None` (raises `CameraError`)

- [ ] **Step 1: Write the failing tests** — `tests/test_assistant_tools.py`

```python
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
        build_proposal(
            camera, {"changes": [{"name": "iso", "value": "400", "reason": "r"}]}, "c"
        )


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_assistant_tools.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lensmind.assistant.tools'`.

- [ ] **Step 3: Implement** — `src/lensmind/assistant/tools.py`

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_assistant_tools.py -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lensmind/assistant/tools.py tests/test_assistant_tools.py
git commit -m "Add the assistant's camera tools and proposal validation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Prompts and the conversation loop

**Files:**
- Create: `src/lensmind/assistant/prompts.py`
- Create: `src/lensmind/assistant/loop.py`
- Test: `tests/test_assistant_loop.py`

**Interfaces:**
- Consumes: everything produced by Tasks 2 and 3.
- Produces:
  - `prompts.system_prompt(lang: str) -> str`, `prompts.msg(lang: str, key: str, **params) -> str`, `prompts.proposal_outcome(proposal: Proposal) -> str`
  - `loop.AssistantError(message: str, status: int = 500)` with `.message`, `.status`
  - `loop.Turn(reply: str, proposal: Proposal | None = None, question: str | None = None, finished: bool = False, limit_reached: bool = False)`
  - `loop.Conversation` with `.id`, `.history`, `.pending_results`, `.awaiting_answer`, `.proposal`, `.lock`
  - `loop.Assistant(camera: Camera, provider: Provider, lang: str, max_turns: int, max_conversations: int = 20)` with `start() -> Conversation`, `get(id) -> Conversation`, `send(id, text) -> Turn`, `apply(id, proposal_id) -> Proposal`

- [ ] **Step 1: Write the failing tests** — `tests/test_assistant_loop.py`

```python
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
    assistant, _, provider, cid = make(
        [state, state2, reply(text_block("Go on."))], max_turns=2
    )
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_assistant_loop.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'lensmind.assistant.loop'`.

- [ ] **Step 3: Implement `src/lensmind/assistant/prompts.py`**

```python
"""System prompt, user-facing strings of the assistant layer, and texts for the model."""

from lensmind.assistant.tools import Proposal

LANGUAGE_NAMES = {"it": "Italian", "en": "English"}

SYSTEM_PROMPT = """\
You are lensmind, an assistant that sets up a camera connected to this device by USB.
The user says what they want to photograph; you choose the camera settings for it.

How to work:
- Call get_camera_state before proposing anything. Use only setting names and values it
  reports: allowed values change with the mode dial and the lens. Ask for other settings
  by name when you need them.
- Propose changes with propose_settings, one entry per setting, each with a short reason
  the user can understand. The user approves or declines the proposal as a whole and
  nothing changes before that. Never say a change was applied until a tool result says so.
- Read-only settings cannot be changed in the current mode. When the goal needs something
  only the user can do (turning the mode dial, zooming, moving, framing, using the flash),
  call ask_user with one clear request.
- If a proposal is rejected, read the allowed values in the error and correct it.
- Call finish when the request is done, with a short summary.
- Keep replies short: the user reads them on a phone, next to the viewfinder.
- Always write to the user in {language}.
"""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "session_not_found": "Conversazione non trovata: ricomincia",
        "proposal_not_found": "Proposta non trovata",
        "proposal_not_pending": "Questa proposta non si può più applicare",
        "busy": "L'assistente sta ancora rispondendo al messaggio precedente",
        "turn_limit": (
            "Mi fermo qui: ho raggiunto il limite di {turns} passaggi per messaggio. "
            "Dimmi come vuoi proseguire."
        ),
        "provider_error": "L'assistente non è raggiungibile ({error}). Riprova.",
        "incomplete": "L'assistente non ha completato la risposta ({error}). Riprova.",
    },
    "en": {
        "session_not_found": "Conversation not found: start again",
        "proposal_not_found": "Proposal not found",
        "proposal_not_pending": "This proposal can no longer be applied",
        "busy": "The assistant is still answering the previous message",
        "turn_limit": (
            "Stopping here: I reached the limit of {turns} steps per message. "
            "Tell me how you want to continue."
        ),
        "provider_error": "The assistant cannot be reached ({error}). Try again.",
        "incomplete": "The assistant did not finish its reply ({error}). Try again.",
    },
}


def system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.format(language=LANGUAGE_NAMES.get(lang, "English"))


def msg(lang: str, key: str, **params: object) -> str:
    return MESSAGES.get(lang, MESSAGES["en"])[key].format(**params)


def proposal_outcome(proposal: Proposal) -> str:
    """Result of `propose_settings` for the model, sent with the user's next message."""
    applied = ", ".join(f"{change.name}={change.new}" for change in proposal.applied)
    if proposal.state == "applied":
        return f"The user approved the proposal. Applied: {applied}."
    if proposal.state in ("partial", "failed") and proposal.failed is not None:
        name, detail = proposal.failed
        done = f"Applied: {applied}." if applied else "Nothing was applied."
        return (
            f"The user approved the proposal. {done} {name} failed: {detail}. "
            "The changes after it were not attempted."
        )
    return "Not applied: the user wrote a new message instead of approving."
```

- [ ] **Step 4: Implement `src/lensmind/assistant/loop.py`**

```python
"""Conversations with the assistant: the model loop, its limits, the approval gate."""

import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from lensmind.assistant.prompts import msg, proposal_outcome, system_prompt
from lensmind.assistant.provider import Block, Provider, ProviderError, ToolCall
from lensmind.assistant.tools import (
    TOOLS,
    Proposal,
    ProposalRejected,
    ProposalState,
    build_proposal,
    camera_state,
    check_changes,
)
from lensmind.camera.base import Camera, CameraError

# Stop reasons of a finished reply; anything else (refusal, max_tokens) is an error.
COMPLETE = frozenset({"end_turn", "tool_use", "stop_sequence"})


class AssistantError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class IncompleteReply(ProviderError):
    """The model stopped for a reason other than finishing its reply."""


@dataclass
class Turn:
    reply: str
    proposal: Proposal | None = None
    question: str | None = None
    finished: bool = False
    limit_reached: bool = False


@dataclass
class Conversation:
    id: str
    history: list[Block] = field(default_factory=list)
    # Tool results not sent yet: they open the next user message.
    pending_results: list[Block] = field(default_factory=list)
    # ask_user calls: the user's next text is their result.
    awaiting_answer: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _Snapshot:
    length: int
    pending_results: list[Block]
    awaiting_answer: list[str]
    proposal: Proposal | None
    proposal_state: ProposalState | None
    proposal_reported: bool


@dataclass
class _Step:
    """What running the tool calls of one reply produced."""

    results: list[Block] = field(default_factory=list)
    proposal: Proposal | None = None
    question: str | None = None
    summary: str | None = None
    finished: bool = False

    @property
    def stops(self) -> bool:
        return self.proposal is not None or self.question is not None or self.finished


def tool_result(tool_use_id: str, content: str, error: bool = False) -> Block:
    block: Block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        block["is_error"] = True
    return block


class Assistant:
    def __init__(
        self,
        camera: Camera,
        provider: Provider,
        lang: str,
        max_turns: int,
        max_conversations: int = 20,
    ) -> None:
        self._camera = camera
        self._provider = provider
        self._lang = lang
        self._max_turns = max_turns
        self._max_conversations = max_conversations
        self._system = system_prompt(lang)
        self._conversations: OrderedDict[str, Conversation] = OrderedDict()
        self._registry_lock = threading.Lock()

    def start(self) -> Conversation:
        conversation = Conversation(id=uuid.uuid4().hex)
        with self._registry_lock:
            while len(self._conversations) >= self._max_conversations:
                self._conversations.popitem(last=False)
            self._conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        with self._registry_lock:
            conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise AssistantError(msg(self._lang, "session_not_found"), 404)
        return conversation

    def send(self, conversation_id: str, text: str) -> Turn:
        conversation = self.get(conversation_id)
        if not conversation.lock.acquire(blocking=False):
            raise AssistantError(msg(self._lang, "busy"), 409)
        try:
            snapshot = _snapshot(conversation)
            try:
                return self._send(conversation, text)
            except ProviderError as error:
                _restore(conversation, snapshot)
                key = "incomplete" if isinstance(error, IncompleteReply) else "provider_error"
                raise AssistantError(msg(self._lang, key, error=error), 502) from error
        finally:
            conversation.lock.release()

    def apply(self, conversation_id: str, proposal_id: str) -> Proposal:
        conversation = self.get(conversation_id)
        if not conversation.lock.acquire(blocking=False):
            raise AssistantError(msg(self._lang, "busy"), 409)
        try:
            proposal = conversation.proposal
            if proposal is None or proposal.id != proposal_id:
                raise AssistantError(msg(self._lang, "proposal_not_found"), 404)
            if proposal.state != "pending":
                raise AssistantError(msg(self._lang, "proposal_not_pending"), 409)
            check_changes(self._camera, proposal.changes, self._lang)
            for change in proposal.changes:
                try:
                    self._camera.set(change.name, change.new)
                except CameraError as error:
                    proposal.failed = (change.name, error.message)
                    proposal.state = "partial" if proposal.applied else "failed"
                    return proposal
                proposal.applied.append(change)
            proposal.state = "applied"
            return proposal
        finally:
            conversation.lock.release()

    # Internals -----------------------------------------------------------------

    def _send(self, conversation: Conversation, text: str) -> Turn:
        blocks = [*conversation.pending_results]
        blocks += [tool_result(call_id, text) for call_id in conversation.awaiting_answer]
        proposal = conversation.proposal
        if proposal is not None and not proposal.reported:
            if proposal.state == "pending":
                proposal.state = "superseded"
            blocks.append(tool_result(proposal.tool_use_id, proposal_outcome(proposal)))
            proposal.reported = True
        conversation.pending_results, conversation.awaiting_answer = [], []
        blocks.append({"type": "text", "text": text})

        last_text = ""
        for _ in range(self._max_turns):
            conversation.history.append({"role": "user", "content": blocks})
            reply = self._provider.complete(self._system, conversation.history, TOOLS)
            if reply.stop_reason not in COMPLETE:
                raise IncompleteReply(reply.stop_reason)
            conversation.history.append({"role": "assistant", "content": reply.content})
            last_text = reply.text
            step = self._run_tools(conversation, reply.tool_calls)
            if step.stops or not reply.tool_calls:
                conversation.pending_results = step.results
                return Turn(
                    reply=_join(last_text, step.question, step.summary),
                    proposal=step.proposal,
                    question=step.question,
                    finished=step.finished,
                )
            blocks = step.results
        conversation.pending_results = blocks
        limit = msg(self._lang, "turn_limit", turns=self._max_turns)
        return Turn(reply=_join(last_text, limit), limit_reached=True)

    def _run_tools(self, conversation: Conversation, calls: list[ToolCall]) -> _Step:
        step = _Step()
        for call in calls:
            if call.name == "get_camera_state":
                step.results.append(self._camera_state(call))
            elif call.name == "propose_settings":
                self._propose(conversation, call, step)
            elif call.name == "ask_user":
                question = str(call.input.get("question", "")).strip()
                if not question:
                    step.results.append(tool_result(call.id, "question is empty", error=True))
                    continue
                conversation.awaiting_answer.append(call.id)
                step.question = _join(step.question, question)
            elif call.name == "finish":
                step.results.append(tool_result(call.id, "ok"))
                step.summary = str(call.input.get("summary", "")).strip() or None
                step.finished = True
            else:
                step.results.append(tool_result(call.id, f"Unknown tool: {call.name}", True))
        return step

    def _camera_state(self, call: ToolCall) -> Block:
        names = call.input.get("names")
        if names is not None and not (
            isinstance(names, list) and all(isinstance(name, str) for name in names)
        ):
            return tool_result(call.id, "names must be a list of setting names", error=True)
        try:
            state = camera_state(self._camera, names or None)
        except CameraError as error:
            return tool_result(call.id, error.message, error=True)
        return tool_result(call.id, json.dumps(state, ensure_ascii=False))

    def _propose(self, conversation: Conversation, call: ToolCall, step: _Step) -> None:
        if step.proposal is not None:
            text = "Only one proposal per reply: this one was ignored."
            step.results.append(tool_result(call.id, text, error=True))
            return
        try:
            proposal = build_proposal(self._camera, call.input, call.id)
        except ProposalRejected as rejected:
            lines = "\n".join(f"- {error}" for error in rejected.errors)
            text = f"Proposal rejected, nothing was shown to the user:\n{lines}"
            step.results.append(tool_result(call.id, text, error=True))
        except CameraError as error:
            step.results.append(tool_result(call.id, error.message, error=True))
        else:
            conversation.proposal = step.proposal = proposal


def _join(*parts: str | None) -> str:
    return "\n\n".join(part for part in parts if part)


def _snapshot(conversation: Conversation) -> _Snapshot:
    proposal = conversation.proposal
    return _Snapshot(
        length=len(conversation.history),
        pending_results=conversation.pending_results,
        awaiting_answer=conversation.awaiting_answer,
        proposal=proposal,
        proposal_state=proposal.state if proposal else None,
        proposal_reported=proposal.reported if proposal else False,
    )


def _restore(conversation: Conversation, snapshot: _Snapshot) -> None:
    del conversation.history[snapshot.length :]
    conversation.pending_results = snapshot.pending_results
    conversation.awaiting_answer = snapshot.awaiting_answer
    conversation.proposal = snapshot.proposal
    if snapshot.proposal is not None and snapshot.proposal_state is not None:
        snapshot.proposal.state = snapshot.proposal_state
        snapshot.proposal.reported = snapshot.proposal_reported
```

Note on `_join(step.question, question)`: several `ask_user` calls in one reply are shown as one message, separated by a blank line.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_assistant_loop.py -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lensmind/assistant/prompts.py src/lensmind/assistant/loop.py tests/test_assistant_loop.py
git commit -m "Add the assistant conversation loop with approval gate and turn limit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Assistant HTTP API

**Files:**
- Modify: `src/lensmind/api/schemas.py`
- Modify: `src/lensmind/api/messages.py`
- Create: `src/lensmind/api/routes_assistant.py`
- Modify: `src/lensmind/api/app.py`
- Modify: `src/lensmind/api/routes_camera.py` (`get_status`)
- Test: `tests/test_api_assistant.py`

**Interfaces:**
- Consumes: `Assistant`, `AssistantError`, `Turn` (Task 4); `Proposal` (Task 3); `Provider`, `ClaudeProvider` (Task 2); `Settings.assistant_ready`, `.anthropic_api_key`, `.model`, `.max_turns` (Task 1).
- Produces: `create_app(settings=None, camera_factory=None, web_dir=WEB_DIR, provider=None)`; `app.state.assistant: Assistant | None`; `StatusOut.assistant: bool`; JSON shapes used by Task 6:
  - `POST /api/assistant/sessions` → 201 `{"id": str}`
  - `POST /api/assistant/sessions/{id}/messages` `{"text"}` → `{"reply", "proposal", "question", "finished", "limit_reached"}`
  - `POST /api/assistant/sessions/{id}/proposals/{pid}/apply` → proposal
  - proposal: `{"id", "summary", "state", "changes": [{"name", "label", "old", "new", "reason"}], "applied": [str], "failed": {"name", "detail"} | null}`

- [ ] **Step 1: Write the failing tests** — `tests/test_api_assistant.py`

```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lensmind.api.app import create_app
from lensmind.assistant.provider import (
    FakeProvider,
    ModelReply,
    ProviderError,
    reply,
    text_block,
    tool_use_block,
)
from lensmind.camera.mock import MockCamera
from lensmind.settings import Settings

PROPOSE_ISO = tool_use_block(
    "p1",
    "propose_settings",
    summary="Brighter",
    changes=[{"name": "iso", "value": "400", "reason": "Dim room"}],
)


def settings_for(tmp_path: Path) -> Settings:
    return Settings(mock=True, language="en", photos_dir=tmp_path)


@pytest.fixture
def camera() -> MockCamera:
    return MockCamera(lang="en")


def client_for(
    tmp_path: Path, camera: MockCamera, script: list[ModelReply | Exception]
) -> TestClient:
    app = create_app(
        settings_for(tmp_path), camera_factory=lambda: camera, provider=FakeProvider(script)
    )
    return TestClient(app)


def iso(client: TestClient) -> str:
    groups = client.get("/api/settings").json()["groups"]
    return next(s["value"] for g in groups for s in g["settings"] if s["name"] == "iso")


def test_status_reports_the_assistant(tmp_path: Path, camera: MockCamera) -> None:
    with client_for(tmp_path, camera, []) as client:
        assert client.get("/api/status").json()["assistant"] is True
    with TestClient(create_app(settings_for(tmp_path))) as client:
        assert client.get("/api/status").json()["assistant"] is False


def test_not_configured_leaves_manual_controls_working(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path))) as client:
        response = client.post("/api/assistant/sessions")
        assert response.status_code == 503
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]
        assert client.put("/api/settings/iso", json={"value": "400"}).status_code == 200
        assert client.post("/api/capture").status_code == 200


def test_proposal_applied_only_after_approval(tmp_path: Path, camera: MockCamera) -> None:
    with client_for(tmp_path, camera, [reply(text_block("Raise ISO."), PROPOSE_ISO)]) as client:
        response = client.post("/api/assistant/sessions")
        assert response.status_code == 201
        sid = response.json()["id"]

        body = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "dark"}).json()
        assert body["reply"] == "Raise ISO."
        assert body["finished"] is False
        assert body["limit_reached"] is False
        proposal = body["proposal"]
        assert proposal["state"] == "pending"
        assert proposal["changes"] == [
            {"name": "iso", "label": "ISO Speed", "old": "100", "new": "400", "reason": "Dim room"}
        ]
        assert iso(client) == "100"

        url = f"/api/assistant/sessions/{sid}/proposals/{proposal['id']}/apply"
        applied = client.post(url)
        assert applied.status_code == 200
        assert applied.json()["state"] == "applied"
        assert applied.json()["applied"] == ["iso"]
        assert applied.json()["failed"] is None
        assert iso(client) == "400"
        assert client.post(url).status_code == 409


def test_unknown_session_and_proposal(tmp_path: Path, camera: MockCamera) -> None:
    with client_for(tmp_path, camera, []) as client:
        response = client.post("/api/assistant/sessions/nope/messages", json={"text": "hi"})
        assert response.status_code == 404
        sid = client.post("/api/assistant/sessions").json()["id"]
        assert client.post(f"/api/assistant/sessions/{sid}/proposals/x/apply").status_code == 404


@pytest.mark.parametrize("text", ["   ", "x" * 2001])
def test_message_text_is_validated(tmp_path: Path, camera: MockCamera, text: str) -> None:
    with client_for(tmp_path, camera, []) as client:
        sid = client.post("/api/assistant/sessions").json()["id"]
        response = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": text})
        assert response.status_code == 422


def test_provider_error_is_502(tmp_path: Path, camera: MockCamera) -> None:
    with client_for(tmp_path, camera, [ProviderError("down")]) as client:
        sid = client.post("/api/assistant/sessions").json()["id"]
        response = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
        assert response.status_code == 502
        assert "down" in response.json()["detail"]


def test_apply_after_the_dial_moved(tmp_path: Path, camera: MockCamera) -> None:
    propose = tool_use_block(
        "p1",
        "propose_settings",
        summary="Freeze",
        changes=[{"name": "shutterspeed2", "value": "1/60", "reason": "r"}],
    )
    with client_for(tmp_path, camera, [reply(propose)]) as client:
        sid = client.post("/api/assistant/sessions").json()["id"]
        body = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "x"}).json()
        camera.turn_dial("A")
        url = f"/api/assistant/sessions/{sid}/proposals/{body['proposal']['id']}/apply"
        response = client.post(url)
        assert response.status_code == 409
        assert "shutterspeed2" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api_assistant.py -q`
Expected: FAIL (`TypeError: create_app() got an unexpected keyword argument 'provider'`).

- [ ] **Step 3: Implement schemas** — `src/lensmind/api/schemas.py`

Change the imports at the top:

```python
from dataclasses import asdict
from typing import Annotated, Self
from urllib.parse import quote

from pydantic import BaseModel, StringConstraints

from lensmind.assistant.loop import Turn
from lensmind.assistant.tools import Proposal
from lensmind.camera.base import CameraStatus, Setting, SettingGroup
from lensmind.storage import Shot
```

Add `assistant: bool = False` as the last field of `StatusOut`, and append:

```python
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
```

- [ ] **Step 4: Implement messages and routes**

`src/lensmind/api/messages.py`:

```python
MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "photo_not_found": "Foto non trovata: {name}",
        "assistant_not_configured": (
            "Assistente non configurato: imposta ANTHROPIC_API_KEY e LENSMIND_MODEL"
        ),
    },
    "en": {
        "photo_not_found": "Photo not found: {name}",
        "assistant_not_configured": (
            "Assistant not configured: set ANTHROPIC_API_KEY and LENSMIND_MODEL"
        ),
    },
}
```

`src/lensmind/api/routes_assistant.py`:

```python
"""Assistant endpoints. Sync: model and camera calls block, FastAPI runs them in its thread pool."""

from fastapi import APIRouter, HTTPException, Request

from lensmind.api.messages import msg
from lensmind.api.schemas import MessageIn, ProposalOut, SessionOut, TurnOut
from lensmind.assistant.loop import Assistant

router = APIRouter(prefix="/api/assistant")


def _assistant(request: Request) -> Assistant:
    assistant: Assistant | None = request.app.state.assistant
    if assistant is None:
        language = request.app.state.settings.language
        raise HTTPException(503, detail=msg(language, "assistant_not_configured"))
    return assistant


@router.post("/sessions", status_code=201)
def start_session(request: Request) -> SessionOut:
    return SessionOut(id=_assistant(request).start().id)


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: str, body: MessageIn, request: Request) -> TurnOut:
    return TurnOut.from_turn(_assistant(request).send(session_id, body.text))


@router.post("/sessions/{session_id}/proposals/{proposal_id}/apply")
def apply_proposal(session_id: str, proposal_id: str, request: Request) -> ProposalOut:
    return ProposalOut.from_model(_assistant(request).apply(session_id, proposal_id))
```

`src/lensmind/api/routes_camera.py` — in `get_status`, pass the flag in both returns:

```python
@router.get("/status")
def get_status(request: Request) -> StatusOut:
    language = _language(request)
    assistant = request.app.state.assistant is not None
    try:
        status = _session(request).status()
    except CameraError as error:
        return StatusOut(
            connected=False, detail=error.message, language=language, assistant=assistant
        )
    return StatusOut(
        connected=True,
        language=language,
        camera=CameraStatusOut.from_model(status),
        assistant=assistant,
    )
```

Update `tests/test_api.py::test_status_when_camera_missing`: its expected dict gains `"assistant": False`.

- [ ] **Step 5: Wire the app** — `src/lensmind/api/app.py`

Imports:

```python
from lensmind.api.routes_assistant import router as assistant_router
from lensmind.api.routes_camera import router as camera_router
from lensmind.assistant.loop import Assistant, AssistantError
from lensmind.assistant.provider import Provider
from lensmind.camera.base import Camera, CameraError
```

Replace `camera_error_handler` with:

```python
async def error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CameraError | AssistantError)
    return JSONResponse(status_code=error.status, content={"detail": error.message})


def provider_for(settings: Settings) -> Provider | None:
    if settings.anthropic_api_key is None or settings.model is None:
        return None
    from lensmind.assistant.provider import ClaudeProvider

    return ClaudeProvider(settings.anthropic_api_key, settings.model)
```

`create_app` gains `provider: Provider | None = None` (last parameter). In the lifespan, after `app.state.store = ...`:

```python
        chosen = provider if provider is not None else provider_for(config)
        app.state.assistant = (
            Assistant(session, chosen, config.language, config.max_turns) if chosen else None
        )
```

and after creating the app:

```python
    app.add_exception_handler(CameraError, error_handler)
    app.add_exception_handler(AssistantError, error_handler)
    app.include_router(camera_router)
    app.include_router(assistant_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: all pass (old API tests included).

- [ ] **Step 7: Commit**

```bash
git add src/lensmind/api tests/test_api_assistant.py tests/test_api.py
git commit -m "Expose the assistant over HTTP

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Conversation panel in the web app

**Files:**
- Create: `web/js/chat_logic.js`
- Create: `web/js/assistant.js`
- Modify: `web/js/api.js`, `web/js/app.js`, `web/js/i18n.js`, `web/index.html`, `web/style.css`
- Test: `tests/test_web_logic.py`, `tests/test_web_static.py`

**Interfaces:**
- Consumes: the JSON shapes listed in Task 5; `status.assistant` from `/api/status`; `el`, `toast` (`ui.js`); `refreshSettings` (`store.js`); `t` (`i18n.js`).
- Produces: `chat_logic.js` exports `cardState(proposal, current)`, `changeLine(change)`, `formatValue(value)`, `sendMessage(client, sessionId, text) -> Promise<{sessionId, turn}>`; `assistant.js` exports `initAssistant()`, `setAssistantAvailable(flag)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web_logic.py` — replace the `POLICY` constant and `evaluate` with a version that takes the module and the imported names, and awaits the expression (top-level await works in module scripts):

```python
NODE = shutil.which("node")
WEB_JS = Path(__file__).resolve().parents[1] / "web" / "js"

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def evaluate(
    expression: str,
    module: str = "policy",
    names: str = "afterFrameError, MAX_FRAME_FAILURES",
) -> object:
    url = (WEB_JS / f"{module}.js").as_uri()
    script = (
        f"import {{ {names} }} from '{url}';"
        f"console.log(JSON.stringify(await ({expression})));"
    )
    assert NODE is not None
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)
```

Append:

```python
CHAT = "chat_logic"


def test_pending_card_is_superseded_once_not_current() -> None:
    states = evaluate(
        "[cardState({state: 'pending'}, true), cardState({state: 'pending'}, false),"
        " cardState({state: 'applied'}, false), cardState({state: 'partial'}, true)]",
        CHAT,
        "cardState",
    )
    assert states == ["pending", "superseded", "applied", "partial"]


def test_change_line() -> None:
    lines = evaluate(
        "[changeLine({name: 'iso', label: 'ISO Speed', old: '100', new: '400'}),"
        " changeLine({name: 'burstnumber', label: '', old: 1.0, new: 3})]",
        CHAT,
        "changeLine",
    )
    assert lines == ["ISO Speed: 100 → 400", "burstnumber: 1 → 3"]


FAKE_CLIENT = """{
  started: 0,
  async startChat() { this.started += 1; return { id: 'new' + this.started }; },
  async sendChat(id, text) {
    if (id === 'old') { const error = new Error('gone'); error.status = 404; throw error; }
    if (text === 'fail') { const error = new Error('down'); error.status = 502; throw error; }
    return { reply: id + ':' + text };
  },
}"""


def test_send_starts_a_session_when_there_is_none() -> None:
    result = evaluate(f"sendMessage({FAKE_CLIENT}, null, 'hi')", CHAT, "sendMessage")
    assert result == {"sessionId": "new1", "turn": {"reply": "new1:hi"}}


def test_send_restarts_once_when_the_server_forgot_the_session() -> None:
    result = evaluate(f"sendMessage({FAKE_CLIENT}, 'old', 'hi')", CHAT, "sendMessage")
    assert result == {"sessionId": "new1", "turn": {"reply": "new1:hi"}}


def test_send_reports_other_errors() -> None:
    expression = (
        f"sendMessage({FAKE_CLIENT}, 'kept', 'fail').then(() => 'ok', (e) => e.status)"
    )
    assert evaluate(expression, CHAT, "sendMessage") == 502
```

`tests/test_web_static.py`:

```python
MODULES = [
    "app",
    "api",
    "i18n",
    "ui",
    "store",
    "viewfinder",
    "tiles",
    "controls",
    "gallery",
    "assistant",
    "chat_logic",
]
```

and in `test_index_loads_the_app` extend the id list:

```python
    for element_id in [
        "vf-img",
        "vf-overlay",
        "tiles",
        "shutter",
        "groups",
        "grid",
        "sheet",
        "chat",
        "composer",
        "chat-input",
        "assistant-off",
    ]:
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_logic.py tests/test_web_static.py -q`
Expected: FAIL (missing `chat_logic.js`, `assistant.js`, ids).

- [ ] **Step 3: Implement `web/js/chat_logic.js`**

```js
// Pure decisions of the assistant panel, kept free of the DOM so they can be tested with Node.

// How a proposal card looks: the server state, except that a proposal still pending
// after a newer message was accepted can no longer be applied.
export function cardState(proposal, current) {
  if (proposal.state === "pending" && !current) return "superseded";
  return proposal.state;
}

export function formatValue(value) {
  return typeof value === "number" ? String(Number(value.toFixed(3))) : String(value);
}

// One change as "Label: old → new".
export function changeLine(change) {
  return `${change.label || change.name}: ${formatValue(change.old)} → ${formatValue(change.new)}`;
}

// Send `text`, starting a session when there is none. A 404 means the server restarted
// and forgot the conversation: start a new one and send once more.
export async function sendMessage(client, sessionId, text) {
  let id = sessionId ?? (await client.startChat()).id;
  try {
    return { sessionId: id, turn: await client.sendChat(id, text) };
  } catch (error) {
    if (error.status !== 404) throw error;
    id = (await client.startChat()).id;
    return { sessionId: id, turn: await client.sendChat(id, text) };
  }
}
```

- [ ] **Step 4: Implement `web/js/assistant.js`**

```js
// The assistant conversation on the main screen: messages, proposals, approval.
import { api } from "./api.js";
import { cardState, changeLine, sendMessage } from "./chat_logic.js";
import { t } from "./i18n.js";
import { refreshSettings } from "./store.js";
import { el, toast } from "./ui.js";

let sessionId = null;
let available = false;
let busy = false;
let latest = null; // { proposal, card, session, current } of the newest proposal

export function initAssistant() {
  document.getElementById("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text || busy || !available) return;
    input.value = "";
    send(text);
  });
  document.getElementById("chat-new").addEventListener("click", () => {
    if (busy) return;
    sessionId = null;
    latest = null;
    document.getElementById("chat").replaceChildren();
  });
  updateComposer();
}

export function setAssistantAvailable(flag) {
  available = flag;
  updateComposer();
}

function updateComposer() {
  document.getElementById("chat-input").disabled = !available;
  document.getElementById("chat-send").disabled = !available || busy;
  document.getElementById("chat-new").disabled = !available || busy;
  document.getElementById("assistant-off").hidden = available;
}

function append(node) {
  document.getElementById("chat").append(node);
  node.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return node;
}

function bubble(kind, text) {
  return append(el("p", { className: `msg ${kind}`, text }));
}

async function send(text) {
  busy = true;
  updateComposer();
  bubble("user", text);
  const thinking = bubble("assistant thinking", t("thinking"));
  try {
    const result = await sendMessage(api, sessionId, text);
    sessionId = result.sessionId;
    // Only now has the server accepted the message: an unapproved proposal is superseded.
    if (latest) {
      latest.current = false;
      renderCard(latest);
    }
    thinking.remove();
    const turn = result.turn;
    if (turn.reply) bubble(turn.question ? "assistant question" : "assistant", turn.reply);
    if (turn.proposal) {
      const card = append(el("div", { className: "proposal" }));
      latest = { proposal: turn.proposal, card, session: sessionId, current: true };
      renderCard(latest);
    }
  } catch (error) {
    thinking.remove();
    bubble("error", error.message);
  } finally {
    busy = false;
    updateComposer();
  }
}

function stateText(proposal, state) {
  const failed = proposal.failed ?? { name: "", detail: "" };
  if (state === "applied") return t("proposal_applied");
  if (state === "partial") return t("proposal_partial", failed);
  if (state === "failed") return t("proposal_failed", failed);
  return t("proposal_superseded");
}

function renderCard(entry) {
  const { proposal, card } = entry;
  const state = cardState(proposal, entry.current);
  const rows = proposal.changes.map((change) =>
    el(
      "li",
      {},
      el("span", { className: "change", text: changeLine(change) }),
      el("span", { className: "reason", text: change.reason }),
    ),
  );
  const footer =
    state === "pending"
      ? el("button", { type: "button", text: t("apply"), onclick: (event) => apply(entry, event.currentTarget) })
      : el("p", { className: state === "applied" ? "proposal-state ok" : "proposal-state", text: stateText(proposal, state) });
  card.replaceChildren(el("p", { className: "proposal-summary", text: proposal.summary }), el("ul", {}, ...rows), footer);
}

async function apply(entry, button) {
  button.disabled = true;
  try {
    entry.proposal = await api.applyProposal(entry.session, entry.proposal.id);
    renderCard(entry);
    refreshSettings().catch(() => {});
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
}
```

- [ ] **Step 5: Wire API, app, strings, markup and styles**

`web/js/api.js` — add to the `api` object:

```js
  startChat: async () => (await request("POST", "/api/assistant/sessions")).json(),
  sendChat: async (id, text) =>
    (await request("POST", `/api/assistant/sessions/${encodeURIComponent(id)}/messages`, { text })).json(),
  applyProposal: async (id, proposalId) =>
    (
      await request(
        "POST",
        `/api/assistant/sessions/${encodeURIComponent(id)}/proposals/${encodeURIComponent(proposalId)}/apply`,
      )
    ).json(),
```

`web/js/app.js`:
- add `import { initAssistant, setAssistantAvailable } from "./assistant.js";` (right after the `./api.js` import, keeping imports sorted by path);
- in `refreshStatus`, right after `if (status.language) setLanguage(status.language);` add `setAssistantAvailable(Boolean(status.assistant));`;
- in `init`, after `initControls();` add `initAssistant();`.

`web/js/i18n.js` — add to `it`:

```js
    chat_placeholder: "Cosa vuoi fotografare?",
    send: "Invia",
    new_chat: "Nuova conversazione",
    thinking: "Sto pensando…",
    assistant_off: "Assistente non configurato: imposta ANTHROPIC_API_KEY e LENSMIND_MODEL",
    apply: "Applica",
    proposal_applied: "Applicata ✓",
    proposal_partial: "Applicata in parte: {name} non riuscita ({detail})",
    proposal_failed: "Non applicata: {name} ({detail})",
    proposal_superseded: "Superata dal nuovo messaggio",
```

and to `en`:

```js
    chat_placeholder: "What do you want to shoot?",
    send: "Send",
    new_chat: "New conversation",
    thinking: "Thinking…",
    assistant_off: "Assistant not configured: set ANTHROPIC_API_KEY and LENSMIND_MODEL",
    apply: "Apply",
    proposal_applied: "Applied ✓",
    proposal_partial: "Partly applied: {name} failed ({detail})",
    proposal_failed: "Not applied: {name} ({detail})",
    proposal_superseded: "Superseded by your new message",
```

In `setLanguage`, after the `data-i18n-label` loop:

```js
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  }
```

`web/index.html` — replace the `#assistant` block:

```html
      <div class="assistant" id="assistant">
        <p id="last-result"></p>
        <p class="assistant-off" id="assistant-off" data-i18n="assistant_off" hidden></p>
        <div class="chat" id="chat" aria-live="polite"></div>
        <form class="composer" id="composer">
          <input id="chat-input" type="text" autocomplete="off" enterkeyhint="send" maxlength="2000" data-i18n-placeholder="chat_placeholder">
          <button class="icon-btn" id="chat-send" type="submit" data-i18n-label="send">➤</button>
          <button class="icon-btn" id="chat-new" type="button" data-i18n-label="new_chat">↺</button>
        </form>
      </div>
```

`web/style.css` — add `max-height: 40dvh;` to the `.viewfinder` rule, and after the `.assistant` rule:

```css
.assistant-off { margin: 0 0 8px; }
.chat { display: flex; flex-direction: column; gap: 8px; margin: 8px 0; }
.msg { max-width: 85%; margin: 0; padding: 10px 12px; border-radius: var(--radius); color: var(--text); overflow-wrap: anywhere; white-space: pre-wrap; }
.msg.user { align-self: flex-end; background: var(--surface-2); }
.msg.assistant { align-self: flex-start; background: var(--surface); }
.msg.question { border-left: 4px solid var(--accent); }
.msg.thinking { color: var(--muted); }
.msg.error { align-self: stretch; max-width: none; border-left: 4px solid var(--danger); background: var(--surface); }
.proposal { padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); color: var(--text); }
.proposal-summary { margin: 0 0 8px; font-weight: 600; }
.proposal ul { display: grid; gap: 8px; margin: 0 0 12px; padding: 0; list-style: none; }
.change { display: block; font-variant-numeric: tabular-nums; }
.reason { display: block; color: var(--muted); font-size: 14px; }
.proposal button { width: 100%; min-height: 48px; border: 0; border-radius: 10px; background: var(--accent); color: #000; font: inherit; font-weight: 600; }
.proposal button:disabled { opacity: 0.5; }
.proposal-state { margin: 0; color: var(--muted); }
.proposal-state.ok { color: var(--ok); }
.composer {
  position: sticky;
  bottom: calc(var(--bar-h) + env(safe-area-inset-bottom));
  z-index: 4;
  display: flex;
  gap: 8px;
  padding: 8px 0;
  background: var(--bg);
}
.composer input {
  flex: 1;
  min-width: 0;
  min-height: 48px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: var(--surface-2);
  color: var(--text);
  font: inherit;
}
.composer .icon-btn { flex: none; }
.composer :disabled { opacity: 0.5; }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: all pass (Node tests run because `node` is installed).

- [ ] **Step 7: Smoke-test the running app against the mock**

Run in the background: `LENSMIND_MOCK=1 LENSMIND_PHOTOS_DIR=$TMPDIR/lm .venv/bin/lensmind`
Then:
`curl -s localhost:8000/api/status` → contains `"assistant":false`;
`curl -s -X POST localhost:8000/api/assistant/sessions` → 503 with the Italian "Assistente non configurato" detail;
`curl -s localhost:8000/js/assistant.js | head -1` → the module comment.
Stop the server.

- [ ] **Step 8: Commit**

```bash
git add web tests/test_web_logic.py tests/test_web_static.py
git commit -m "Add the assistant conversation panel to the web app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Documentation and final verification

**Files:**
- Modify: `CLAUDE.md` ("Current status" line)
- Modify: `README.md` (usage of the assistant)

- [ ] **Step 1: Update docs**

`CLAUDE.md`, replace the status line:

```markdown
Current status: phase 1 and phase 2 implemented; hardware checklist in
docs/cameras/nikon-d3500.md; phase 2 still to be tried with a real API key.
```

`README.md`: in the "try it without a camera" section, after `LENSMIND_MOCK=1 lensmind`, add:

```markdown
To try the assistant too, set an API key and a model:

    ANTHROPIC_API_KEY=... LENSMIND_MODEL=<model id> LENSMIND_MOCK=1 lensmind

Write what you want to shoot; the assistant proposes settings with a reason for each,
and nothing changes on the camera until you press Apply.
```

- [ ] **Step 2: Full verification**

Run: `.venv/bin/python -m pytest -q && .venv/bin/ruff format . && .venv/bin/ruff check .`
Expected: everything passes; report the test count.

Run: `grep -rn "import anthropic\|from anthropic" src` → only `src/lensmind/assistant/provider.py`.
Run: `grep -rn "fastapi" src/lensmind/assistant src/lensmind/camera` → no matches.
Run: `grep -rn "claude-" src` → no model identifiers.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document phase 2: the assistant by words

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Hand-off to the user**

Manual check that only the user can run (needs network and a key): with `LENSMIND_MOCK=1`, `ANTHROPIC_API_KEY` and `LENSMIND_MODEL` set, open the web app on a phone, write "ritratto, sfondo sfocato", check that a proposal with one reason per change appears, that the tiles do not change until Apply, and that they change after it.
