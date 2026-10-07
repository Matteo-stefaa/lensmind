from pathlib import Path

from lensmind.camera.dump import DumpEntry, entry_to_setting, parse_dump

DUMPS = Path(__file__).resolve().parents[1] / "docs" / "cameras" / "d3500"


def load(mode: str) -> list[DumpEntry]:
    return parse_dump((DUMPS / f"d3500-config-{mode}.txt").read_text(encoding="utf-8"))


def by_path(entries: list[DumpEntry], path: str) -> DumpEntry:
    return next(entry for entry in entries if entry.path == path)


def test_parses_every_widget() -> None:
    assert len(load("M")) == 117


def test_choice_entry() -> None:
    entry = by_path(load("M"), "/main/capturesettings/f-number")
    assert entry.type == "RADIO"
    assert entry.readonly is False
    assert entry.current == "f/3.5"
    assert entry.choices[0] == "f/3.5"
    assert entry.choices[-1] == "f/22"
    assert len(entry.choices) == 17
    assert entry.section == "capturesettings"
    assert entry.name == "f-number"


def test_readonly_and_choices_differ_per_mode() -> None:
    entry = by_path(load("AUTO"), "/main/capturesettings/f-number")
    assert entry.readonly is True
    assert entry.choices[0] == "f/1"


def test_range_entry() -> None:
    entry = by_path(load("M"), "/main/capturesettings/burstnumber")
    assert (entry.bottom, entry.top, entry.step) == (1.0, 100.0, 1.0)
    assert entry.current == "1"


def test_empty_current_value() -> None:
    assert by_path(load("M"), "/main/settings/thumbsize").current == ""


def test_entry_to_setting_converts_types() -> None:
    entries = load("M")
    date = entry_to_setting(by_path(entries, "/main/settings/datetime"))
    toggle = entry_to_setting(by_path(entries, "/main/settings/fastfs"))
    shots = entry_to_setting(by_path(entries, "/main/status/availableshots"))
    iso = entry_to_setting(by_path(entries, "/main/imgsettings/iso"))
    assert date is not None and date.type == "date" and isinstance(date.value, int)
    assert toggle is not None and toggle.type == "toggle" and toggle.value == 1
    assert shots is not None and shots.type == "range" and shots.readonly
    assert isinstance(shots.value, float)
    assert iso is not None and iso.type == "choice" and iso.choices is not None
    assert iso.min is None
