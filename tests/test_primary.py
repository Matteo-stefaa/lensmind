from lensmind.camera.base import Setting, SettingGroup
from lensmind.camera.primary import resolve_primary


def group(*names: str) -> SettingGroup:
    return SettingGroup("g", "G", [Setting(name, name, "text", "", False) for name in names])


def test_prefers_first_candidate() -> None:
    assert resolve_primary([group("shutterspeed", "shutterspeed2")])["shutter"] == "shutterspeed2"


def test_falls_back_to_later_candidates() -> None:
    primary = resolve_primary([group("shutterspeed", "aperture")])
    assert primary == {"shutter": "shutterspeed", "aperture": "aperture"}


def test_searches_all_groups_and_omits_missing_roles() -> None:
    primary = resolve_primary([group("iso"), group("expprogram")])
    assert primary == {"iso": "iso", "mode": "expprogram"}
