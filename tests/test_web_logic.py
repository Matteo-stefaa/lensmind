"""Pure web-app logic, run with Node (skipped where Node is not installed)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
POLICY = (Path(__file__).resolve().parents[1] / "web" / "js" / "policy.js").as_uri()

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def evaluate(expression: str) -> object:
    script = (
        f"import {{ afterFrameError, MAX_FRAME_FAILURES }} from '{POLICY}';"
        f"console.log(JSON.stringify({expression}));"
    )
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
