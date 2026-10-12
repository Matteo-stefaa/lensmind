from pathlib import Path

import pytest

from lensmind.settings import Settings


def test_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.mock is False
    assert settings.mock_dial == "M"
    assert (settings.host, settings.port) == ("0.0.0.0", 8000)
    assert settings.language == "it"
    assert settings.photos_dir == Path("~/lensmind-photos").expanduser()
    assert settings.liveview_idle_seconds == 5.0
    assert settings.anthropic_api_key is None
    assert settings.model is None
    assert settings.max_turns == 6


def test_reads_every_variable(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "LENSMIND_MOCK": "1",
            "LENSMIND_MOCK_DIAL": "auto",
            "LENSMIND_HOST": "127.0.0.1",
            "LENSMIND_PORT": "80",
            "LENSMIND_LANGUAGE": "en",
            "LENSMIND_PHOTOS_DIR": str(tmp_path),
            "LENSMIND_LIVEVIEW_IDLE_SECONDS": "2.5",
        }
    )
    assert settings.mock is True
    assert settings.mock_dial == "AUTO"
    assert (settings.host, settings.port) == ("127.0.0.1", 80)
    assert settings.language == "en"
    assert settings.photos_dir == tmp_path
    assert settings.liveview_idle_seconds == 2.5


@pytest.mark.parametrize(
    "env",
    [
        {"LENSMIND_LANGUAGE": "fr"},
        {"LENSMIND_MOCK_DIAL": "S"},
        {"LENSMIND_PORT": "eighty"},
        {"LENSMIND_MAX_TURNS": "0"},
    ],
)
def test_rejects_invalid_values(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_main_runs_uvicorn_with_configured_address(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import uvicorn

    from lensmind.__main__ import main

    calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: calls.update(host=host, port=port))
    monkeypatch.setenv("LENSMIND_MOCK", "1")
    monkeypatch.setenv("LENSMIND_PORT", "8123")
    monkeypatch.setenv("LENSMIND_PHOTOS_DIR", str(tmp_path))
    main()
    assert calls == {"host": "0.0.0.0", "port": 8123}


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
