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
