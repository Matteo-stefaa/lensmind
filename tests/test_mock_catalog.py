from lensmind.camera.base import Setting
from lensmind.camera.mock_catalog import load_catalog


def all_settings() -> list[Setting]:
    return [setting for group in load_catalog() for setting in group.settings]


def test_groups_exclude_actions_and_other() -> None:
    names = [group.name for group in load_catalog()]
    assert names == ["settings", "status", "imgsettings", "capturesettings"]


def test_fifty_real_settings_plus_mock_artist() -> None:
    names = [setting.name for setting in all_settings()]
    assert len(names) == 51
    assert "artist" in names
    assert len(set(names)) == len(names)


def test_every_type_is_writable_somewhere() -> None:
    writable = {setting.type for setting in all_settings() if not setting.readonly}
    assert writable == {"choice", "range", "toggle", "text", "date"}


def test_initial_values_give_a_sensible_exposure() -> None:
    values = {setting.name: setting.value for setting in all_settings()}
    assert values["shutterspeed2"] == "1/125"
    assert values["shutterspeed"] == "0.0080s"
    assert values["f-number"] == "f/5.6"
    assert values["iso"] == "100"
    assert values["exposurecompensation"] == "0"


def test_shutter_lists_are_parallel() -> None:
    settings = {setting.name: setting for setting in all_settings()}
    long_names = settings["shutterspeed"].choices
    short_names = settings["shutterspeed2"].choices
    assert long_names is not None and short_names is not None
    # In M the D3500 offers 52 timed speeds plus "Bulb" and "Time".
    assert len(long_names) == len(short_names) == 54
    assert long_names[-2:] == short_names[-2:] == ["Bulb", "Time"]
