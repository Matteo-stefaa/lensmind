from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lensmind.api.app import create_app
from lensmind.camera.base import CameraDisconnected
from lensmind.camera.mock import MockCamera
from lensmind.settings import Settings


def settings_for(tmp_path: Path, mock_dial: str = "M") -> Settings:
    return Settings(mock=True, mock_dial=mock_dial, language="en", photos_dir=tmp_path)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings_for(tmp_path))) as test_client:
        yield test_client


def test_status_connected(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body["connected"] is True
    assert body["language"] == "en"
    assert body["camera"]["model"] == "D3500"


def test_status_when_camera_missing(tmp_path: Path) -> None:
    def missing() -> MockCamera:
        raise CameraDisconnected("Camera not connected", 503)

    with TestClient(create_app(settings_for(tmp_path), camera_factory=missing)) as test_client:
        response = test_client.get("/api/status")
        assert response.status_code == 200
        assert response.json() == {
            "connected": False,
            "detail": "Camera not connected",
            "language": "en",
            "camera": None,
        }
        assert test_client.get("/api/settings").status_code == 503


def test_settings_and_primary(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    groups = [g["name"] for g in body["groups"]]
    assert groups == ["settings", "status", "imgsettings", "capturesettings"]
    assert body["primary"]["shutter"] == "shutterspeed2"
    assert body["primary"]["aperture"] == "f-number"
    assert body["primary"]["mode"] == "expprogram"


def test_put_setting(client: TestClient) -> None:
    response = client.put("/api/settings/iso", json={"value": "400"})
    assert response.status_code == 200
    assert response.json()["value"] == "400"
    settings = client.get("/api/settings").json()["groups"]
    iso = next(s for g in settings for s in g["settings"] if s["name"] == "iso")
    assert iso["value"] == "400"


def test_put_every_type(client: TestClient) -> None:
    for name, value in [
        ("burstnumber", 3),
        ("fastfs", False),
        ("artist", "M"),
        ("datetime", 1800000000),
    ]:
        assert client.put(f"/api/settings/{name}", json={"value": value}).status_code == 200


def test_put_value_with_slash_round_trips(client: TestClient) -> None:
    response = client.put("/api/settings/shutterspeed2", json={"value": "10/25"})
    assert response.status_code == 200
    assert response.json()["value"] == "10/25"


def test_put_wrong_json_type_is_422(client: TestClient) -> None:
    for name, value in [("iso", 400), ("burstnumber", "3")]:
        response = client.put(f"/api/settings/{name}", json={"value": value})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)
        assert name in response.json()["detail"]


def test_put_errors_map_to_status(client: TestClient) -> None:
    unknown = client.put("/api/settings/nope", json={"value": "x"})
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "Unknown setting: nope"}
    assert client.put("/api/settings/batterylevel", json={"value": "1%"}).status_code == 409


def test_capture_and_download(client: TestClient) -> None:
    shot = client.post("/api/capture").json()
    assert [f["name"].rsplit("_", 1)[1] for f in shot["files"]] == ["0001.JPG", "0001.NEF"]
    thumb = client.get(shot["thumb_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    raw = client.get(shot["files"][1]["url"])
    assert raw.status_code == 200
    assert raw.content.startswith(b"lensmind mock NEF")


def test_photos_lists_newest_first(client: TestClient) -> None:
    client.post("/api/capture")
    client.post("/api/capture")
    shots = client.get("/api/photos?limit=1").json()
    assert len(shots) == 1
    assert shots[0]["id"].endswith("DSC_0002")


def test_photo_not_found(client: TestClient) -> None:
    assert client.get("/api/photos/missing.jpg").status_code == 404
    assert client.get("/api/photos/.thumbs").status_code == 404
    assert client.get("/api/photos/missing.jpg/thumb").status_code == 404


def test_preview_is_an_uncached_jpeg(client: TestClient) -> None:
    response = client.get("/api/preview")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.content[:2] == b"\xff\xd8"


def test_preview_refused_in_auto(tmp_path: Path) -> None:
    with TestClient(create_app(settings_for(tmp_path, mock_dial="AUTO"))) as test_client:
        response = test_client.get("/api/preview")
        assert response.status_code == 409
        assert "P/A/S/M" in response.json()["detail"]


def test_liveview_stop(client: TestClient) -> None:
    client.get("/api/preview")
    assert client.post("/api/liveview/stop").status_code == 204
    assert client.get("/api/status").json()["camera"]["liveview_active"] is False


def test_web_app_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
