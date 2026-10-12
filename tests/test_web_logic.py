"""Pure web-app logic, run with Node (skipped where Node is not installed)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB_JS = Path(__file__).resolve().parents[1] / "web" / "js"

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def evaluate(
    expression: str,
    module: str = "policy",
    names: str = "afterFrameError, MAX_FRAME_FAILURES",
) -> object:
    url = (WEB_JS / f"{module}.js").as_uri()
    script = f"import {{ {names} }} from '{url}';console.log(JSON.stringify(await ({expression})));"
    assert NODE is not None
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_live_view_keeps_going_through_a_busy_camera() -> None:
    delays = evaluate("[afterFrameError(503, 1), afterFrameError(0, 2), afterFrameError(500, 3)]")
    assert isinstance(delays, list)
    assert all(isinstance(delay, int) and delay > 0 for delay in delays)


def test_live_view_stops_when_the_camera_refuses_it() -> None:
    assert evaluate("afterFrameError(409, 1)") is None


def test_live_view_stops_after_repeated_failures() -> None:
    assert evaluate("afterFrameError(503, MAX_FRAME_FAILURES)") is None


def test_retry_delay_grows_and_is_capped() -> None:
    delays = evaluate("[1, 2, 3, 4].map((n) => afterFrameError(503, n))")
    assert isinstance(delays, list)
    assert delays == sorted(delays)
    assert max(delays) <= 2000


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
    expression = f"sendMessage({FAKE_CLIENT}, 'kept', 'fail').then(() => 'ok', (e) => e.status)"
    assert evaluate(expression, CHAT, "sendMessage") == 502
