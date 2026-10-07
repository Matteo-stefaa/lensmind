"""Settings of the simulated camera, loaded from a real Nikon D3500 dump (dial on M)."""

from dataclasses import replace
from importlib import resources

from lensmind.camera.base import EXCLUDED_SECTIONS, Setting, SettingGroup
from lensmind.camera.dump import entry_to_setting, parse_dump

DUMP_RESOURCE = "data/nikon-d3500-M.txt"

# libgphoto2 section labels (the dump only contains section names).
GROUP_LABELS = {
    "settings": "Camera Settings",
    "status": "Camera Status Information",
    "imgsettings": "Image Settings",
    "capturesettings": "Capture Settings",
}

# The dump was taken at 20 s and -4.7 EV; start from a correct exposure instead
# (1/125, f/5.6, ISO 100 matches the mock scene at EV100 12).
INITIAL: dict[str, str] = {
    "shutterspeed2": "1/125",
    "shutterspeed": "0.0080s",
    "f-number": "f/5.6",
    "iso": "100",
    "exposurecompensation": "0",
}


def load_catalog() -> list[SettingGroup]:
    text = resources.files("lensmind.camera").joinpath(DUMP_RESOURCE).read_text(encoding="utf-8")
    sections: dict[str, list[Setting]] = {}
    seen: set[str] = set()
    for entry in parse_dump(text):
        if entry.section in EXCLUDED_SECTIONS or entry.name in seen:
            continue
        setting = entry_to_setting(entry)
        if setting is None:
            continue
        seen.add(setting.name)
        if setting.name in INITIAL:
            setting = replace(setting, value=INITIAL[setting.name])
        sections.setdefault(entry.section, []).append(setting)
    # Mock-only: the D3500 exposes no writable text setting, and the web app must be
    # able to exercise every setting type.
    sections["settings"].append(Setting("artist", "Artist", "text", "", False))
    return [
        SettingGroup(name, GROUP_LABELS.get(name, name), items) for name, items in sections.items()
    ]
