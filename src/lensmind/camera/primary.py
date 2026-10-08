"""The only hardcoded setting names: roles shown as main tiles, with fallbacks."""

from lensmind.camera.base import SettingGroup

PRIMARY: dict[str, tuple[str, ...]] = {
    "shutter": ("shutterspeed2", "shutterspeed"),
    "aperture": ("f-number", "aperture"),
    "iso": ("iso",),
    "exposure_comp": ("exposurecompensation",),
    "white_balance": ("whitebalance",),
    "focus": ("focusmode2", "focusmode"),
    "quality": ("imagequality",),
    "mode": ("expprogram",),
}


def resolve_primary(groups: list[SettingGroup]) -> dict[str, str]:
    """Map each role to the first candidate name the camera exposes."""
    names = {setting.name for group in groups for setting in group.settings}
    resolved: dict[str, str] = {}
    for role, candidates in PRIMARY.items():
        found = next((name for name in candidates if name in names), None)
        if found is not None:
            resolved[role] = found
    return resolved
