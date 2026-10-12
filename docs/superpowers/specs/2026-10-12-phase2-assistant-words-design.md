# Phase 2 — Assistant by words: design

Date: 2026-10-12
Status: approved in conversation, pending written review

Scope: `assistant/` (provider, tools, loop, prompts), `api/routes_assistant.py`, the
assistant panel in `web/`, new configuration in `settings.py`. No image evaluation
(phase 3), no automatic application or test shots (phase 4).

Done when:

1. `pytest` passes with the mock camera and the fake provider (no network, `anthropic`
   not required);
2. a text request produces a validated proposal with a reason per change;
3. nothing is applied to the camera without the user pressing Apply;
4. manually, with `LENSMIND_MOCK=1` and a real key, a request in the web app produces a
   reasoned proposal that is applied only after approval.

## 1. Decisions

| Topic | Decision |
|---|---|
| AI access | Official `anthropic` SDK, sync client, hand-written tool loop (no `tool_runner`) |
| Approval | All or nothing: one Apply button per proposal; changes are asked for in words |
| After apply | Outcome returned to the UI at once; reaches the model with the next user message (no extra model call) |
| Reply language | `LENSMIND_LANGUAGE`, enforced by the system prompt |
| Conversations | In memory, single user, lost on restart |
| Model identifier | `LENSMIND_MODEL`, required, no default in code |

## 2. Configuration — `settings.py`

| Field | Variable | Default |
|---|---|---|
| `anthropic_api_key` | `ANTHROPIC_API_KEY` (the only unprefixed variable) | `None` |
| `model` | `LENSMIND_MODEL` | `None` |
| `max_turns` | `LENSMIND_MAX_TURNS` | `6` (model calls per user message, must be ≥ 1) |

`Settings.assistant_ready` is true only when both key and model are set. Empty strings
count as unset. `__repr__` must not print the key.

## 3. Assistant layer

### 3.1 `assistant/provider.py`

The only module that imports `anthropic`, lazily inside `ClaudeProvider.__init__`.

Neutral types, so the rest of `assistant/` never sees SDK types:

```python
@dataclass(frozen=True)
class TextBlock:
    text: str

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]

@dataclass(frozen=True)
class ModelReply:
    blocks: list[TextBlock | ToolCall]
    stop_reason: str

class ProviderError(Exception): ...

class Provider(Protocol):
    def complete(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> ModelReply: ...
```

`messages` uses the Messages API shape (`role`, `content` blocks with `text`,
`tool_use`, `tool_result`), stored as plain dicts.

- `ClaudeProvider(api_key, model)`: `anthropic.Anthropic(...).messages.create`, with
  `cache_control` on the system prompt and the last tool so the static prefix is cached.
  Any SDK exception is re-raised as `ProviderError`.
- `FakeProvider(script)`: returns scripted `ModelReply` objects in order, records each
  request, and asserts on every call that the history is valid: roles alternate, and
  every `tool_use` in an assistant message is answered by a `tool_result` with the same
  id in the next user message. Running out of script raises `AssertionError`.

### 3.2 `assistant/tools.py`

Tool schemas (JSON Schema, sent to the model) and their execution through `Camera`.

| Tool | Input | Behaviour |
|---|---|---|
| `get_camera_state` | `names?: list[str]` | Without `names`: every resolved primary role (`resolve_primary`) with name, label, type, value, readonly, choices or min/max/step; the camera status (model, battery); and the names of all writable settings. With `names`: the same detail for those settings; unknown names are reported, not fatal. |
| `propose_settings` | `changes: [{name, value, reason}]`, `summary: str` | Validates, then stores the proposal and pauses the loop. |
| `ask_user` | `question: str` | Pauses the loop; the question is shown to the user. |
| `finish` | `summary: str` | Ends the turn; the summary is shown to the user. |

`propose_settings` validation, against `camera.settings()` read at that moment:

- each value through `camera.base.validate()` (unknown → 404 message, read-only → 409
  message, outside choices/range → 422 message listing the allowed values);
- `changes` not empty, no duplicate names, non-empty `reason`, value different from the
  current one;
- all errors are collected and returned together as one tool error (`is_error: true`);
  nothing is stored. The model may retry within the turn limit.

On success a `Proposal` is built:

```python
@dataclass
class Change:
    name: str
    label: str
    old: SettingValue
    new: SettingValue      # coerced by validate()
    reason: str

@dataclass
class Proposal:
    id: str
    summary: str
    changes: list[Change]
    state: Literal["pending", "applied", "partial", "failed", "superseded"]
```

### 3.3 `assistant/prompts.py`

- `system_prompt(lang)`: role (camera assistant for the connected camera), process
  (read state first, propose only valid values, one reason per change, use `ask_user`
  for physical actions such as the mode dial, zoom, framing, flash; never claim a change
  was applied before the user approves), and the reply language.
- `msg(lang, key, **params)`: user-facing strings of the assistant layer (turn limit
  reached, not configured, session not found, proposal not found, busy, proposal no
  longer pending, provider error), Italian and English, same pattern as
  `camera/messages.py`.
- Tool-result texts for the model (proposal applied / partially applied / not applied)
  are in English: they are for the model, not the user.

### 3.4 `assistant/loop.py`

```python
@dataclass
class Turn:
    reply: str
    proposal: Proposal | None
    question: str | None
    finished: bool
    limit_reached: bool

@dataclass
class ApplyResult:
    applied: list[Change]
    failed: tuple[str, str] | None   # (name, detail)

class Conversation:
    id: str
    history: list[dict]
    pending_results: list[dict]      # tool_result blocks not yet sent
    proposal: Proposal | None
    lock: threading.Lock

class Assistant:
    def __init__(self, camera: Camera, provider: Provider, lang: str, max_turns: int,
                 max_conversations: int = 20) -> None: ...
    def start(self) -> Conversation: ...
    def get(self, conversation_id: str) -> Conversation: ...   # AssistantError 404
    def send(self, conversation_id: str, text: str) -> Turn: ...
    def apply(self, conversation_id: str, proposal_id: str) -> ApplyResult: ...
```

`AssistantError(message, status)` mirrors `CameraError`. The registry keeps at most
`max_conversations` and evicts the oldest.

`send`:

1. Acquire the conversation lock without blocking; if held → `AssistantError` 409.
2. Snapshot `history`, `pending_results` and the proposal state for rollback.
3. Build the user turn: `pending_results` first, then the text block.
   - A pending proposal still in `pending` state becomes `superseded`; its tool result
     says it was not applied because the user wrote something else.
   - A proposal applied since the last message: its tool result carries the outcome
     (applied values, or partial with the failed setting and reason).
   - A pending `ask_user`: its tool result is the user's text.
4. Loop for at most `max_turns` model calls. For each reply, append it to history and
   execute every tool call in order:
   - `get_camera_state`, or an invalid `propose_settings` → result appended now;
   - valid `propose_settings` → proposal stored, result deferred, loop stops after this
     reply;
   - `ask_user` → result deferred, loop stops;
   - `finish` → result `"ok"` appended to `pending_results`, loop stops, `finished`;
   - unknown tool → error result.
   If the reply has no tool calls, the loop stops. Results produced now go into one user
   message; if the loop continues it is sent with the next call, otherwise it goes into
   `pending_results`.
5. Limit hit → stop with the "turn limit reached" message, `limit_reached = true`; any
   unanswered results stay in `pending_results`.
6. `reply` is the concatenated text blocks of the last model reply, plus the `ask_user`
   question or `finish` summary when present.
7. `ProviderError` → restore the snapshot, raise `AssistantError` 502.

Camera calls hold the camera lock only for their own duration; no lock is held while
waiting for the model.

`apply`:

1. Unknown proposal → 404. Proposal not the conversation's current one, or not
   `pending` → 409.
2. Read `camera.settings()` once and validate every change against it. Any failure →
   raise the `CameraError` (422/409/404); nothing is written; state stays `pending`.
3. Write changes in order with `camera.set`. On a `CameraError`, stop: state `partial`
   (some applied) or `failed` (none), record the failing name and message.
4. Otherwise state `applied`.
5. The outcome is queued as the proposal's tool result for the next `send`.

## 4. HTTP API — `api/routes_assistant.py`

| Method | Path | Body → response |
|---|---|---|
| GET | `/api/status` | adds `assistant: bool` (`assistant_ready`) |
| POST | `/api/assistant/sessions` | → `{id}` |
| POST | `/api/assistant/sessions/{id}/messages` | `{text}` (1–2000 chars) → `{reply, proposal?, question?, finished, limit_reached}` |
| POST | `/api/assistant/sessions/{id}/proposals/{pid}/apply` | → `{state, applied: [{name, value}], failed?: {name, detail}}` |

`proposal` in responses: `{id, summary, changes: [{name, label, old, new, reason}]}`.

Errors, body `{"detail": "..."}` in the configured language:

| Case | Status |
|---|---|
| Assistant not configured | 503 |
| Unknown session or proposal | 404 |
| Conversation busy; proposal superseded or already applied | 409 |
| Value no longer valid at apply time | 422 (from `CameraError`) |
| Provider error | 502 |

- Endpoints are sync functions, like the camera ones.
- `create_app(..., provider: Provider | None = None)`. In the lifespan, if a provider is
  given or `assistant_ready`, an `Assistant` is built on the `CameraSession` and stored
  in `app.state.assistant`; otherwise `app.state.assistant = None` and the assistant
  endpoints return 503.
- `AssistantError` gets an exception handler like `CameraError`.

## 5. Web app

- New `web/js/assistant.js`: conversation list, input, send, new conversation (↺). The
  session is created on the first message.
- Main screen: viewfinder shorter, tiles, scrollable conversation, input row above the
  bottom bar. The shutter stays where it is.
- Bubbles built with `textContent`. An `ask_user` question is an emphasised assistant
  bubble; the answer is typed in the same input.
- Proposal card: per change the label, `old → new` and the reason below; one **Apply**
  button. After apply: "Applied ✓", or the failed row with its detail; then
  `refreshSettings()` so the tiles update. A newer message marks the card "Superseded"
  and disables the button.
- While waiting: "thinking…" indicator, send disabled.
- `assistant: false` in status: input disabled, with a message explaining that
  `ANTHROPIC_API_KEY` and `LENSMIND_MODEL` must be set. Manual controls unchanged.
- Pure logic (card state from proposal state, `old → new` formatting) in a module
  testable with Node, like `policy.js`.
- New strings in `i18n.js`.

## 6. Dependencies

`anthropic` added to the main dependencies in `pyproject.toml`. It is imported only by
`ClaudeProvider`, so tests and mock mode run without it. Installation on the Pi (wheels
for `jiter` and `pydantic-core` on aarch64) is checked during deployment and recorded in
the docs.

## 7. Tests

All with the mock camera and `FakeProvider`.

- `tests/test_assistant_tools.py`: `get_camera_state` content with and without
  `names`; `propose_settings` rejects unknown, read-only, out-of-choices, out-of-range,
  duplicate, empty reason and unchanged values, with the allowed values in the error.
- `tests/test_assistant_loop.py`: invalid value → tool error → model corrects → valid
  proposal; settings unchanged until apply; apply writes; superseded or applied proposal
  → 409; a change made invalid before apply (mock dial switched to A) writes nothing;
  failure midway → partial; `ask_user` pause and resume; apply outcome delivered with the
  next message; turn limit enforced with message; provider error restores history;
  history validity checked by the fake in every scenario.
- `tests/test_api_assistant.py`: endpoints and status codes; 503 when not configured
  while `/api/settings` and `/api/capture` still work; `/api/status.assistant`.
- `tests/test_settings.py`: new variables, `assistant_ready`, key not in repr.
- Node test for the web logic module.
