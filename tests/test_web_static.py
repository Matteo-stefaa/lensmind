import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lensmind.api.app import WEB_DIR, create_app
from lensmind.settings import Settings

MODULES = ["app", "api", "i18n", "ui", "store", "viewfinder", "tiles", "controls", "gallery"]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(mock=True, photos_dir=tmp_path))) as test_client:
        yield test_client


def test_index_loads_the_app(client: TestClient) -> None:
    html = client.get("/").text
    assert 'src="/js/app.js"' in html
    assert 'href="/style.css"' in html
    for element_id in ["vf-img", "vf-overlay", "tiles", "shutter", "groups", "grid", "sheet"]:
        assert f'id="{element_id}"' in html
    assert 'id="toast"' in html


@pytest.mark.parametrize("module", MODULES)
def test_modules_are_served_as_javascript(client: TestClient, module: str) -> None:
    response = client.get(f"/js/{module}.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_no_html_injection_and_no_cdn() -> None:
    for path in [*WEB_DIR.rglob("*.js"), *WEB_DIR.rglob("*.html"), *WEB_DIR.rglob("*.css")]:
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text, path
        assert "insertAdjacentHTML" not in text, path
        assert not re.search(r"https?://", text), path


def test_overlays_do_not_catch_touches() -> None:
    css = (WEB_DIR / "style.css").read_text(encoding="utf-8")
    for selector in [".vf-overlay", ".toast"]:
        block = css.split(selector + " {", 1)[1].split("}", 1)[0]
        assert "pointer-events: none" in block
