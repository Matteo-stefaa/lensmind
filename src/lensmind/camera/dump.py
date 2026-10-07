"""Parser for the text printed by `gphoto2 --list-all-config`."""

from dataclasses import dataclass

from lensmind.camera.base import Setting, SettingType, SettingValue

TYPE_MAP: dict[str, SettingType] = {
    "RADIO": "choice",
    "MENU": "choice",
    "RANGE": "range",
    "TOGGLE": "toggle",
    "TEXT": "text",
    "DATE": "date",
}


@dataclass(frozen=True)
class DumpEntry:
    path: str
    label: str
    readonly: bool
    type: str
    current: str
    choices: tuple[str, ...]
    bottom: float | None
    top: float | None
    step: float | None

    @property
    def section(self) -> str:
        return self.path.split("/")[2]

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[1]


def parse_dump(text: str) -> list[DumpEntry]:
    entries: list[DumpEntry] = []
    fields: dict[str, str] | None = None
    choices: list[str] = []
    for line in text.splitlines():
        if line.startswith("/"):
            fields, choices = {"path": line.strip()}, []
            continue
        if fields is None:
            continue
        if line.strip() == "END":
            entries.append(_entry(fields, choices))
            fields = None
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        value = value[1:] if value.startswith(" ") else value
        if key == "Choice":
            choices.append(value.partition(" ")[2])
        else:
            fields[key] = value
    return entries


def _entry(fields: dict[str, str], choices: list[str]) -> DumpEntry:
    def number(key: str) -> float | None:
        return float(fields[key]) if key in fields else None

    return DumpEntry(
        path=fields["path"],
        label=fields.get("Label", ""),
        readonly=fields.get("Readonly", "0").strip() == "1",
        type=fields.get("Type", "").strip(),
        current=fields.get("Current", ""),
        choices=tuple(choices),
        bottom=number("Bottom"),
        top=number("Top"),
        step=number("Step"),
    )


def entry_to_setting(entry: DumpEntry) -> Setting | None:
    kind = TYPE_MAP.get(entry.type)
    if kind is None:
        return None
    value: SettingValue
    if kind == "range":
        value = float(entry.current)
    elif kind in ("toggle", "date"):
        value = int(entry.current)
    else:
        value = entry.current
    return Setting(
        name=entry.name,
        label=entry.label,
        type=kind,
        value=value,
        readonly=entry.readonly,
        choices=list(entry.choices) if kind == "choice" else None,
        min=entry.bottom if kind == "range" else None,
        max=entry.top if kind == "range" else None,
        step=entry.step if kind == "range" else None,
    )
