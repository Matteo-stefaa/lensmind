# Phase 1 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working lensmind server with no AI: camera layer (mock + libgphoto2), HTTP API, phone web app with manual controls, live view and gallery, and a Raspberry Pi installer.

**Architecture:** `camera/` exposes a `Camera` protocol with two implementations (a mock modelled on real Nikon D3500 dumps, and a libgphoto2 one) behind a `CameraSession` that serialises calls with one lock, reconnects lazily and stops idle live view. A FastAPI app (sync endpoints) wraps the session and a `PhotoStore`; a no-build static web app talks to the API.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, Pillow, python-gphoto2 (Pi only), pytest, httpx (TestClient), ruff; plain HTML/CSS/ES-module JS.

**Spec:** `docs/superpowers/specs/2026-10-07-phase1-foundations-design.md`

## Global Constraints

- Python `>=3.11`; type hints everywhere; `ruff check . && ruff format .` clean.
- Runtime dependencies only `fastapi`, `uvicorn`, `Pillow`; `gphoto2` is the optional extra `pi`; dev extra is `pytest`, `ruff`, `httpx`. Ask before adding anything else.
- Only `src/lensmind/camera/gphoto.py` imports `gphoto2`, and only lazily (inside `GPhotoCamera.__init__`).
- `camera/` never imports FastAPI, Pydantic or `lensmind.settings`. Dependencies point `api → camera`, `api → storage`, `api → settings`.
- Configuration only through `src/lensmind/settings.py`, env vars prefixed `LENSMIND_`.
- User-facing strings in Italian (default) and English, kept in `camera/messages.py`, `api/messages.py` and `web/js/i18n.js` only.
- Tests never touch real hardware or the network. On the Mac, create the venv with `/opt/homebrew/bin/python3.11` (system `python3` is 3.9).
- Web app: no build step, no CDN, DOM built with `textContent`/properties only (never `innerHTML`), overlays above controls have `pointer-events: none`, 16 px side gutters, no horizontal scroll, live view stops when the page is hidden.
- Code, comments, commit messages and docs in English. Every commit message ends with:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Review Focus

1. **Shutter pressed while live view is running** → the capture succeeds and the next preview request restarts live view. Test: `test_preview_after_capture_restarts_liveview` (Task 6).
2. **Two shots within the same second** (the mock captures instantly) → no file is overwritten. Test: `test_same_second_does_not_overwrite` (Task 7).
3. **Wrong JSON type for a value** (number for a choice, string for a range) → 422 with a readable `detail`, never 500. Test: `test_put_wrong_json_type_is_422` (Task 8).
4. **Choice values with odd characters** (`"10/25"`, `"Unknown value 000b"`) → round-trip through the API unchanged. Test: `test_put_value_with_slash_round_trips` (Task 8).
5. **Foreign or hidden files in the photos folder** (`.DS_Store`, `notes.txt`) → the gallery still lists shots and does not crash. Test: `test_list_ignores_hidden_and_tolerates_foreign_files` (Task 7).

## File map

```
pyproject.toml, .gitignore
src/lensmind/__init__.py
src/lensmind/__main__.py            # `lensmind` entry point
src/lensmind/settings.py            # Settings.from_env()
src/lensmind/storage.py             # PhotoStore, Shot
src/lensmind/camera/__init__.py
src/lensmind/camera/base.py         # models, Camera protocol, errors, validate(), liveview_block_reason()
src/lensmind/camera/messages.py     # camera-layer user strings
src/lensmind/camera/primary.py      # PRIMARY table, resolve_primary()
src/lensmind/camera/dump.py         # parser for `gphoto2 --list-all-config` text
src/lensmind/camera/data/nikon-d3500-M.txt   # packaged copy of the M-mode dump
src/lensmind/camera/mock_catalog.py # load_catalog() from the packaged dump
src/lensmind/camera/mock_image.py   # synthetic scene renderer
src/lensmind/camera/mock.py         # MockCamera
src/lensmind/camera/session.py      # CameraSession
src/lensmind/camera/gphoto.py       # GPhotoCamera
src/lensmind/api/__init__.py
src/lensmind/api/app.py             # create_app()
src/lensmind/api/schemas.py
src/lensmind/api/routes_camera.py
src/lensmind/api/messages.py
web/index.html, web/style.css
web/js/{app,api,i18n,ui,store,viewfinder,tiles,controls,gallery}.js
deploy/install.sh, deploy/lensmind.service
docs/cameras/d3500/*.txt            # moved from docs/camera/
docs/cameras/nikon-d3500.md
tests/test_*.py, tests/fake_gphoto2.py
```

---

### Task 1: Project setup and camera documentation

**Files:**
- Create: `pyproject.toml`, `src/lensmind/__init__.py`, `src/lensmind/camera/__init__.py`, `src/lensmind/api/__init__.py`, `tests/test_package.py`, `docs/cameras/nikon-d3500.md`
- Move: `docs/camera/*` → `docs/cameras/d3500/`
- Modify: `.gitignore`

**Interfaces:**
- Produces: installable package `lensmind` (src layout, `lensmind.__version__ == "0.1.0"`), console script `lensmind = lensmind.__main__:main` (module written in Task 8), dumps at `docs/cameras/d3500/d3500-config-{M,A,AUTO}.txt`.

- [ ] **Step 1: Move the dumps**

```bash
mkdir -p docs/cameras && git mv docs/camera docs/cameras/d3500 && ls docs/cameras/d3500
```
Expected: `d3500-abilities.txt d3500-config-A.txt d3500-config-AUTO.txt d3500-config-M.txt d3500-summary.txt`

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "lensmind"
version = "0.1.0"
description = "An AI assistant that sets up a tethered camera"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.110", "uvicorn>=0.29", "Pillow>=10.0"]

[project.optional-dependencies]
pi = ["gphoto2>=2.5"]
dev = ["pytest>=8.0", "ruff>=0.5", "httpx>=0.27"]

[project.scripts]
lensmind = "lensmind.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
"lensmind.camera" = ["data/*.txt"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 3: Package skeleton**

`src/lensmind/__init__.py`:
```python
"""lensmind: an AI assistant that sets up a tethered camera."""

__version__ = "0.1.0"
```

`src/lensmind/camera/__init__.py`:
```python
"""Camera access: protocol, models, libgphoto2 and simulated implementations."""
```

`src/lensmind/api/__init__.py`:
```python
"""HTTP API served to the web app."""
```

Append to `.gitignore`:
```
photos/
.mjs.check/
```

- [ ] **Step 4: Write the smoke test**

`tests/test_package.py`:
```python
import lensmind


def test_package_imports() -> None:
    assert lensmind.__version__ == "0.1.0"
```

- [ ] **Step 5: Create the venv, install, run the test**

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```
Expected: `1 passed`

- [ ] **Step 6: Write `docs/cameras/nikon-d3500.md`**

```markdown
# Nikon D3500

Findings from a D3500 (firmware V1.00, AF-P 18-55 kit lens) on a Raspberry Pi 5,
libgphoto2 via the `gphoto2` CLI. Raw dumps: `d3500/`.

## Connection

- Micro-USB port. A charge-only cable shows nothing in `lsusb` and nothing in `dmesg`.
- Detected as "Nikon DSC D3500". `--abilities` lists Image, Preview and Trigger capture.

## Settings per dial position

Same 117 widgets in M, A and AUTO; only read-only flags and some choice lists change.

| Setting | M | A | AUTO |
|---|---|---|---|
| `shutterspeed2`, `shutterspeed` | writable | read-only | read-only |
| `f-number` | writable | writable | read-only |
| `iso`, `exposurecompensation`, `whitebalance`, `focusmode2` | writable | writable | writable (effect not verified) |
| `expprogram`, `focusmode` | read-only | read-only | read-only |
| Live view | allowed | allowed | prohibited |

- `f-number` choices follow the lens in M/A (f/3.5–f/22 at 18 mm); in AUTO the list is
  a generic f/1–f/22.
- `flashmode` choices differ between M and AUTO.
- The dial (`expprogram`) cannot be changed over USB.

## Quirks

- A current value can be outside the choices: `effectmode = "Unknown value 000b"`,
  `thumbsize = ""`.
- Toggles can read `2` (unknown), e.g. `bulb`, `movie`.
- `/main/actions/bulb` appears twice.
- `/main/other/*` are raw PTP properties duplicating readable settings; lensmind hides
  them. `/main/actions/opcode` sends raw PTP commands; lensmind hides all of `actions`.
- `liveviewprohibit` explains why live view is refused, e.g.
  "Live View prohibit conditions: Recording destination card, but no card or card
  protected, Exposure Program Mode is not P/A/S/M". Live view needs an SD card and the
  dial on P/A/S/M.
- `capturetarget = Internal RAM` by default; `imagequality = NEF+Fine` gives two files
  per shot.

## Hardware checklist (to run at the end of phase 1)

- [ ] Live view over USB works in M; frames per second on the phone: …
- [ ] `f-number = f/3.5` with the zoom at 55 mm: result …
- [ ] ISO set in AUTO is honoured in the EXIF of the shot: yes/no …
- [ ] RAW+JPEG: delay between the JPEG and the `GP_EVENT_FILE_ADDED` for the NEF: …
- [ ] Unplug and replug the cable while the app is open: status recovers yes/no …
- [ ] Live view stops on its own a few seconds after closing the page: yes/no …
```

- [ ] **Step 7: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add -A
git commit -m "$(printf 'Set up Python project and document D3500 findings\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 2: Camera models, messages, validation and primary settings

**Files:**
- Create: `src/lensmind/camera/messages.py`, `src/lensmind/camera/base.py`, `src/lensmind/camera/primary.py`
- Test: `tests/test_validate.py`, `tests/test_primary.py`

**Interfaces:**
- Produces (`lensmind.camera.base`): `SettingValue = str | float | int`, `SettingType`, `Setting(name, label, type, value, readonly, choices=None, min=None, max=None, step=None)`, `SettingGroup(name, label, settings)`, `CameraStatus(manufacturer, model, battery, can_preview, liveview_active, liveview_blocked_reason)`, `CapturedFile(name, data)`, `CameraError(message, status=500)` with `.message`/`.status`, `CameraDisconnected(CameraError)`, `Camera` protocol, `EXCLUDED_SECTIONS = frozenset({"actions", "other"})`, `liveview_block_reason(text: str | None) -> str | None`, `validate(setting: Setting | None, name: str, value: object, lang: str) -> SettingValue`.
- Produces (`lensmind.camera.messages`): `msg(lang: str, key: str, **params: object) -> str`.
- Produces (`lensmind.camera.primary`): `PRIMARY: dict[str, tuple[str, ...]]`, `resolve_primary(groups: list[SettingGroup]) -> dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_validate.py`:
```python
import pytest

from lensmind.camera.base import CameraError, Setting, liveview_block_reason, validate

CHOICE = Setting("iso", "ISO Speed", "choice", "100", False, choices=["100", "200", "400"])
RANGE = Setting("burstnumber", "Burst Number", "range", 1.0, False, min=1, max=100, step=1)
TOGGLE = Setting("fastfs", "Fast Filesystem", "toggle", 1, False)
TEXT = Setting("artist", "Artist", "text", "", False)
DATE = Setting("datetime", "Camera Date and Time", "date", 1791393832, False)
READONLY = Setting("batterylevel", "Battery Level", "text", "100%", True)


def error_for(setting: Setting | None, value: object, name: str | None = None) -> CameraError:
    target = name or (setting.name if setting else "missing")
    with pytest.raises(CameraError) as caught:
        validate(setting, target, value, "en")
    return caught.value


def test_unknown_name_is_404() -> None:
    error = error_for(None, "x", name="nope")
    assert error.status == 404
    assert "nope" in error.message


def test_readonly_is_409() -> None:
    assert error_for(READONLY, "50%").status == 409


def test_choice_accepts_listed_value() -> None:
    assert validate(CHOICE, "iso", "200", "en") == "200"


def test_choice_rejects_unlisted_value_and_lists_allowed() -> None:
    error = error_for(CHOICE, "800")
    assert error.status == 422
    assert "100, 200, 400" in error.message


def test_choice_rejects_non_string() -> None:
    assert error_for(CHOICE, 200).status == 422


def test_choice_with_current_value_outside_choices() -> None:
    odd = Setting(
        "effectmode", "Effect Mode", "choice", "Unknown value 000b", False,
        choices=["Night Vision", "Silhouette"],
    )
    assert validate(odd, "effectmode", "Silhouette", "en") == "Silhouette"
    assert error_for(odd, "Unknown value 000b").status == 422


def test_range_coerces_int_to_float() -> None:
    value = validate(RANGE, "burstnumber", 3, "en")
    assert value == 3.0
    assert isinstance(value, float)


@pytest.mark.parametrize("value", [0, 101, 2.5])
def test_range_rejects_out_of_bounds_or_off_step(value: float) -> None:
    error = error_for(RANGE, value)
    assert error.status == 422
    assert "1" in error.message and "100" in error.message


@pytest.mark.parametrize("value", [True, "3"])
def test_range_rejects_bool_and_string(value: object) -> None:
    assert error_for(RANGE, value).status == 422


@pytest.mark.parametrize(("value", "expected"), [(True, 1), (False, 0), (1, 1), (0, 0)])
def test_toggle_coercion(value: object, expected: int) -> None:
    assert validate(TOGGLE, "fastfs", value, "en") == expected


def test_toggle_rejects_unknown_state_two() -> None:
    assert error_for(TOGGLE, 2).status == 422


def test_text_accepts_string() -> None:
    assert validate(TEXT, "artist", "Matteo", "en") == "Matteo"


def test_date_accepts_epoch_seconds() -> None:
    assert validate(DATE, "datetime", 1800000000, "en") == 1800000000


@pytest.mark.parametrize("value", [-1, "now", 1.5, True])
def test_date_rejects_other_values(value: object) -> None:
    assert error_for(DATE, value).status == 422


def test_messages_follow_language() -> None:
    with pytest.raises(CameraError) as caught:
        validate(None, "nope", "x", "it")
    assert "Impostazione sconosciuta" in caught.value.message


def test_liveview_block_reason() -> None:
    blocked = "Live View prohibit conditions: Exposure Program Mode is not P/A/S/M"
    assert liveview_block_reason(blocked) == blocked
    assert liveview_block_reason("Liveview should not be prohibited") is None
    assert liveview_block_reason(None) is None
```

`tests/test_primary.py`:
```python
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_validate.py tests/test_primary.py -q`
Expected: errors, `ModuleNotFoundError: No module named 'lensmind.camera.base'`

- [ ] **Step 3: Write `camera/messages.py`**

```python
"""User-facing messages of the camera layer, per language."""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "unknown_setting": "Impostazione sconosciuta: {name}",
        "readonly": "{name} non si può cambiare in questo momento",
        "expected_text": "{name} richiede un testo",
        "expected_number": "{name} richiede un numero",
        "expected_toggle": "{name} richiede 0 o 1",
        "expected_date": "{name} richiede una data in secondi dal 1970",
        "not_in_choices": "Valore non ammesso per {name}: {value}. Valori ammessi: {allowed}",
        "out_of_range": (
            "Valore non ammesso per {name}: {value}. Ammesso da {min} a {max}, passo {step}"
        ),
        "not_connected": "Fotocamera non collegata",
        "usb_claimed": "La fotocamera è occupata da un altro programma",
        "io_error": "Comunicazione con la fotocamera interrotta ({error})",
        "camera_busy": "La fotocamera è occupata, riprova tra un attimo",
        "not_supported": "Operazione non supportata dalla fotocamera",
        "bad_parameters": "La fotocamera ha rifiutato il valore",
        "camera_error": "Errore della fotocamera ({error})",
    },
    "en": {
        "unknown_setting": "Unknown setting: {name}",
        "readonly": "{name} cannot be changed right now",
        "expected_text": "{name} needs a text value",
        "expected_number": "{name} needs a number",
        "expected_toggle": "{name} needs 0 or 1",
        "expected_date": "{name} needs a date in seconds since 1970",
        "not_in_choices": "Value not allowed for {name}: {value}. Allowed values: {allowed}",
        "out_of_range": (
            "Value not allowed for {name}: {value}. Allowed from {min} to {max}, step {step}"
        ),
        "not_connected": "Camera not connected",
        "usb_claimed": "The camera is held by another process",
        "io_error": "Lost communication with the camera ({error})",
        "camera_busy": "The camera is busy, try again in a moment",
        "not_supported": "Operation not supported by the camera",
        "bad_parameters": "The camera rejected the value",
        "camera_error": "Camera error ({error})",
    },
}


def msg(lang: str, key: str, **params: object) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    return table[key].format(**params)
```

- [ ] **Step 4: Write `camera/base.py`**

```python
"""Camera protocol, data models, errors and the validation shared by all cameras."""

from dataclasses import dataclass
from typing import Literal, Protocol

from lensmind.camera.messages import msg

SettingValue = str | float | int
SettingType = Literal["choice", "range", "toggle", "text", "date"]

# Top-level config sections never exposed: raw PTP properties ("other") and actions
# such as "opcode", which sends arbitrary PTP commands to the camera.
EXCLUDED_SECTIONS = frozenset({"actions", "other"})

# Wording used by libgphoto2's Nikon driver in the "liveviewprohibit" status text.
LIVEVIEW_PROHIBIT_PREFIX = "Live View prohibit conditions"


@dataclass(frozen=True)
class Setting:
    name: str
    label: str
    type: SettingType
    value: SettingValue
    readonly: bool
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None


@dataclass(frozen=True)
class SettingGroup:
    name: str
    label: str
    settings: list[Setting]


@dataclass(frozen=True)
class CameraStatus:
    manufacturer: str
    model: str
    battery: str | None
    can_preview: bool
    liveview_active: bool
    liveview_blocked_reason: str | None


@dataclass(frozen=True)
class CapturedFile:
    name: str
    data: bytes


class CameraError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class CameraDisconnected(CameraError):
    """The connection is lost: the session drops it and reconnects on the next call."""


class Camera(Protocol):
    def status(self) -> CameraStatus: ...
    def settings(self) -> list[SettingGroup]: ...
    def set(self, name: str, value: SettingValue) -> Setting: ...
    def capture(self) -> list[CapturedFile]: ...
    def preview(self) -> bytes: ...
    def end_liveview(self) -> None: ...
    def close(self) -> None: ...


def liveview_block_reason(text: str | None) -> str | None:
    """Return the camera's explanation when its status text says live view is refused."""
    if text and text.startswith(LIVEVIEW_PROHIBIT_PREFIX):
        return text
    return None


def validate(setting: Setting | None, name: str, value: object, lang: str) -> SettingValue:
    """Check a value against the setting as currently reported; return it coerced."""
    if setting is None:
        raise CameraError(msg(lang, "unknown_setting", name=name), 404)
    if setting.readonly:
        raise CameraError(msg(lang, "readonly", name=name), 409)
    if setting.type in ("choice", "text"):
        if not isinstance(value, str):
            raise CameraError(msg(lang, "expected_text", name=name), 422)
        choices = setting.choices or []
        if setting.type == "choice" and value not in choices:
            allowed = ", ".join(choices)
            raise CameraError(
                msg(lang, "not_in_choices", name=name, value=value, allowed=allowed), 422
            )
        return value
    if setting.type == "range":
        return _validate_range(setting, value, lang)
    if setting.type == "toggle":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int) and value in (0, 1):
            return value
        raise CameraError(msg(lang, "expected_toggle", name=name), 422)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CameraError(msg(lang, "expected_date", name=name), 422)
    return value


def _validate_range(setting: Setting, value: object, lang: str) -> float:
    name = setting.name
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CameraError(msg(lang, "expected_number", name=name), 422)
    number = float(value)
    low, high, step = setting.min, setting.max, setting.step
    in_range = (low is None or number >= low) and (high is None or number <= high)
    on_step = True
    if step and low is not None:
        steps = (number - low) / step
        on_step = abs(steps - round(steps)) < 1e-6
    if not (in_range and on_step):
        raise CameraError(
            msg(
                lang, "out_of_range", name=name, value=_fmt(number),
                min=_fmt(low), max=_fmt(high), step=_fmt(step),
            ),
            422,
        )
    return number


def _fmt(number: float | None) -> str:
    return "-" if number is None else f"{number:g}"
```

- [ ] **Step 5: Write `camera/primary.py`**

```python
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
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_validate.py tests/test_primary.py -q`
Expected: all pass.

- [ ] **Step 7: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera tests/test_validate.py tests/test_primary.py
git commit -m "$(printf 'Add camera models, validation and primary settings\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 3: Dump parser and mock catalog

**Files:**
- Create: `src/lensmind/camera/dump.py`, `src/lensmind/camera/mock_catalog.py`, `src/lensmind/camera/data/nikon-d3500-M.txt` (copy)
- Test: `tests/test_dump.py`, `tests/test_mock_catalog.py`

**Interfaces:**
- Consumes: `Setting`, `SettingGroup`, `SettingValue`, `EXCLUDED_SECTIONS` from Task 2.
- Produces (`lensmind.camera.dump`): `DumpEntry(path, label, readonly, type, current, choices: tuple[str, ...], bottom, top, step)` with properties `.section` and `.name`; `parse_dump(text: str) -> list[DumpEntry]`; `TYPE_MAP: dict[str, SettingType]` (`RADIO`/`MENU` → choice, …); `entry_to_setting(entry) -> Setting | None`.
- Produces (`lensmind.camera.mock_catalog`): `load_catalog() -> list[SettingGroup]` (51 settings: 50 from the dump + mock-only `artist`), `INITIAL: dict[str, str]`.

- [ ] **Step 1: Copy the dump into the package**

```bash
mkdir -p src/lensmind/camera/data
cp docs/cameras/d3500/d3500-config-M.txt src/lensmind/camera/data/nikon-d3500-M.txt
```

- [ ] **Step 2: Write the failing tests**

`tests/test_dump.py`:
```python
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
```

`tests/test_mock_catalog.py`:
```python
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
    assert len(long_names) == len(short_names) == 52
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/test_dump.py tests/test_mock_catalog.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.camera.dump'`

- [ ] **Step 4: Write `camera/dump.py`**

```python
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
```

- [ ] **Step 5: Write `camera/mock_catalog.py`**

```python
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
        SettingGroup(name, GROUP_LABELS.get(name, name), items)
        for name, items in sections.items()
    ]
```

- [ ] **Step 6: Run the tests**

Run: `pip install -e ".[dev]" -q && pytest tests/test_dump.py tests/test_mock_catalog.py -q`
Expected: all pass. (Reinstalling picks up the new package data.)

- [ ] **Step 7: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera tests/test_dump.py tests/test_mock_catalog.py
git commit -m "$(printf 'Parse gphoto2 config dumps and build the mock catalog from the D3500\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 4: Synthetic scene renderer for the mock

**Files:**
- Create: `src/lensmind/camera/mock_image.py`
- Test: `tests/test_mock_image.py`

**Interfaces:**
- Produces: `PREVIEW_SIZE = (640, 426)`, `CAPTURE_SIZE = (1500, 1000)`, `render(error_stops: float, size: tuple[int, int]) -> bytes` (JPEG; brightness scales with `2 ** error_stops` in linear light).

- [ ] **Step 1: Write the failing tests**

`tests/test_mock_image.py`:
```python
import io

from PIL import Image, ImageStat

from lensmind.camera.mock_image import PREVIEW_SIZE, render


def luma(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("L")


def mean(data: bytes) -> float:
    return ImageStat.Stat(luma(data)).mean[0]


def fraction(data: bytes, low: int, high: int) -> float:
    histogram = luma(data).histogram()
    return sum(histogram[low : high + 1]) / sum(histogram)


def test_jpeg_of_requested_size() -> None:
    data = render(0.0, PREVIEW_SIZE)
    assert data[:2] == b"\xff\xd8"
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == PREVIEW_SIZE


def test_brightness_increases_with_exposure() -> None:
    means = [mean(render(stops, PREVIEW_SIZE)) for stops in (-2, -1, 0, 1, 2)]
    assert all(darker < brighter for darker, brighter in zip(means, means[1:], strict=False))


def test_overexposure_clips_highlights() -> None:
    assert fraction(render(3, PREVIEW_SIZE), 250, 255) > fraction(render(0, PREVIEW_SIZE), 250, 255) + 0.1


def test_underexposure_crushes_shadows() -> None:
    assert fraction(render(-3, PREVIEW_SIZE), 0, 10) > fraction(render(0, PREVIEW_SIZE), 0, 10) + 0.05


def test_render_is_deterministic() -> None:
    assert render(0.5, PREVIEW_SIZE) == render(0.5, PREVIEW_SIZE)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_mock_image.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.camera.mock_image'`

- [ ] **Step 3: Write `camera/mock_image.py`**

```python
"""Deterministic synthetic scene whose brightness follows the exposure error."""

import io
from functools import lru_cache

from PIL import Image, ImageDraw

PREVIEW_SIZE = (640, 426)
CAPTURE_SIZE = (1500, 1000)
GAMMA = 2.2


@lru_cache(maxsize=4)
def _scene(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    horizon = int(height * 0.62)
    for y in range(horizon):
        k = y / horizon
        draw.line([(0, y), (width, y)], fill=(int(120 + 60 * k), int(160 + 50 * k), int(215 + 20 * k)))
    draw.rectangle([0, horizon, width, height], fill=(70, 95, 55))
    # Sun: the first area to clip when overexposed.
    radius, cx, cy = int(height * 0.08), int(width * 0.8), int(height * 0.18)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(250, 248, 235))
    # Deep shadow: the first area to block up when underexposed.
    draw.rectangle([int(width * 0.05), int(height * 0.45), int(width * 0.25), height], fill=(18, 18, 22))
    # Subject.
    sx, sy, sr = int(width * 0.5), int(height * 0.55), int(height * 0.2)
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(190, 145, 120))
    return image


def render(error_stops: float, size: tuple[int, int]) -> bytes:
    """Return the scene as JPEG, exposed `error_stops` above (or below) correct."""
    factor = 2 ** (max(-10.0, min(10.0, error_stops)) / GAMMA)
    table = [min(255, round(value * factor)) for value in range(256)] * 3
    buffer = io.BytesIO()
    _scene(size).point(table).save(buffer, "JPEG", quality=85)
    return buffer.getvalue()
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_mock_image.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera/mock_image.py tests/test_mock_image.py
git commit -m "$(printf 'Render a synthetic scene that reacts to exposure\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 5: MockCamera

**Files:**
- Create: `src/lensmind/camera/mock.py`
- Test: `tests/test_mock.py`

**Interfaces:**
- Consumes: Task 2 models, `validate`, `liveview_block_reason`, `msg`; `load_catalog()` (Task 3); `render`, `PREVIEW_SIZE`, `CAPTURE_SIZE` (Task 4).
- Produces: `MockCamera(dial: str = "M", lang: str = "it")` implementing `Camera`, plus mock-only `turn_dial(mode: str) -> None` (raises `ValueError` for anything but `"M"`, `"A"`, `"AUTO"`), `simulate_disconnect() -> None`, `exposure_error() -> float`, property `closed: bool`. Constants `DIAL_MODES = ("M", "A", "AUTO")`, `SCENE_EV100 = 12.0`.

- [ ] **Step 1: Write the failing tests**

`tests/test_mock.py`:
```python
import io

import pytest
from PIL import Image, ImageStat

from lensmind.camera.base import CameraDisconnected, CameraError, Setting
from lensmind.camera.mock import MockCamera


@pytest.fixture
def cam() -> MockCamera:
    return MockCamera(dial="M", lang="en")


def get(cam: MockCamera, name: str) -> Setting:
    return next(s for group in cam.settings() for s in group.settings if s.name == name)


def mean(data: bytes) -> float:
    with Image.open(io.BytesIO(data)) as image:
        return ImageStat.Stat(image.convert("L")).mean[0]


def test_status(cam: MockCamera) -> None:
    status = cam.status()
    assert status.model == "D3500"
    assert status.manufacturer == "Nikon Corporation"
    assert status.can_preview
    assert not status.liveview_active
    assert status.liveview_blocked_reason is None


def test_set_validates_like_a_real_camera(cam: MockCamera) -> None:
    for name, value, status in [
        ("iso", "123", 422),
        ("opcode", "0x1001", 404),
        ("batterylevel", "1%", 409),
    ]:
        with pytest.raises(CameraError) as caught:
            cam.set(name, value)
        assert caught.value.status == status


def test_every_writable_type_round_trips(cam: MockCamera) -> None:
    cam.set("iso", "400")
    cam.set("burstnumber", 5)
    cam.set("fastfs", 0)
    cam.set("artist", "Matteo")
    cam.set("datetime", 1800000000)
    assert get(cam, "iso").value == "400"
    assert get(cam, "burstnumber").value == 5.0
    assert get(cam, "fastfs").value == 0
    assert get(cam, "artist").value == "Matteo"
    assert get(cam, "datetime").value == 1800000000


def test_shutter_names_stay_in_sync(cam: MockCamera) -> None:
    cam.set("shutterspeed2", "1/30")
    assert get(cam, "shutterspeed").value == "0.0333s"
    cam.set("shutterspeed", "0.0080s")
    assert get(cam, "shutterspeed2").value == "1/125"


def test_initial_exposure_is_about_right(cam: MockCamera) -> None:
    assert abs(cam.exposure_error()) < 0.3


def test_longer_shutter_overexposes(cam: MockCamera) -> None:
    before = cam.exposure_error()
    cam.set("shutterspeed2", "1/30")
    assert cam.exposure_error() - before == pytest.approx(2.06, abs=0.01)


def test_dial_a_locks_shutter_and_meters(cam: MockCamera) -> None:
    cam.turn_dial("A")
    assert get(cam, "shutterspeed2").readonly
    assert not get(cam, "f-number").readonly
    assert get(cam, "expprogram").value == "A"
    cam.set("f-number", "f/11")
    assert abs(cam.exposure_error()) < 0.2


def test_dial_a_follows_exposure_compensation(cam: MockCamera) -> None:
    cam.turn_dial("A")
    cam.set("exposurecompensation", "1")
    assert cam.exposure_error() == pytest.approx(1.0, abs=0.2)


def test_dial_auto_blocks_liveview_and_locks_exposure(cam: MockCamera) -> None:
    cam.turn_dial("AUTO")
    assert get(cam, "f-number").readonly
    assert get(cam, "shutterspeed2").readonly
    assert get(cam, "f-number").choices[0] == "f/1"
    assert abs(cam.exposure_error()) < 0.2
    with pytest.raises(CameraError) as caught:
        cam.preview()
    assert caught.value.status == 409
    assert "P/A/S/M" in caught.value.message
    assert cam.status().liveview_blocked_reason is not None


def test_dial_back_to_m_restores_lens_apertures(cam: MockCamera) -> None:
    cam.turn_dial("AUTO")
    cam.turn_dial("M")
    assert get(cam, "f-number").choices[0] == "f/3.5"
    assert not get(cam, "shutterspeed2").readonly


def test_turn_dial_rejects_unknown_mode(cam: MockCamera) -> None:
    with pytest.raises(ValueError):
        cam.turn_dial("S")


def test_preview_returns_jpeg_and_tracks_liveview(cam: MockCamera) -> None:
    assert cam.preview()[:2] == b"\xff\xd8"
    assert cam.status().liveview_active
    cam.end_liveview()
    assert not cam.status().liveview_active


def test_capture_raw_plus_jpeg_gives_two_files(cam: MockCamera) -> None:
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG", "DSC_0001.NEF"]


def test_capture_jpeg_only_and_numbering(cam: MockCamera) -> None:
    cam.set("imagequality", "JPEG Fine")
    assert [f.name for f in cam.capture()] == ["DSC_0001.JPG"]
    assert [f.name for f in cam.capture()] == ["DSC_0002.JPG"]


def test_capture_turns_liveview_off(cam: MockCamera) -> None:
    cam.preview()
    cam.capture()
    assert not cam.status().liveview_active


def test_captured_brightness_follows_settings(cam: MockCamera) -> None:
    cam.set("imagequality", "JPEG Fine")
    cam.set("shutterspeed2", "1/4000")
    dark = mean(cam.capture()[0].data)
    cam.set("shutterspeed2", "1/8")
    bright = mean(cam.capture()[0].data)
    assert dark < bright


def test_simulate_disconnect_fails_next_call_only(cam: MockCamera) -> None:
    cam.simulate_disconnect()
    with pytest.raises(CameraDisconnected):
        cam.status()
    assert cam.status().model == "D3500"


def test_close(cam: MockCamera) -> None:
    cam.close()
    assert cam.closed
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_mock.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.camera.mock'`

- [ ] **Step 3: Write `camera/mock.py`**

```python
"""Simulated Nikon D3500: real settings catalog, a dial, and an exposure model."""

import math
from dataclasses import replace

from lensmind.camera.base import (
    CameraDisconnected,
    CameraError,
    CameraStatus,
    CapturedFile,
    Setting,
    SettingGroup,
    SettingValue,
    liveview_block_reason,
    validate,
)
from lensmind.camera.messages import msg
from lensmind.camera.mock_catalog import load_catalog
from lensmind.camera.mock_image import CAPTURE_SIZE, PREVIEW_SIZE, render

DIAL_MODES = ("M", "A", "AUTO")
SCENE_EV100 = 12.0

# Read-only flags that change with the dial, as observed on the D3500.
READONLY_BY_DIAL: dict[str, dict[str, bool]] = {
    "M": {"shutterspeed": False, "shutterspeed2": False, "f-number": False},
    "A": {"shutterspeed": True, "shutterspeed2": True, "f-number": False},
    "AUTO": {"shutterspeed": True, "shutterspeed2": True, "f-number": True},
}
EXPPROGRAM = {"M": "M", "A": "A", "AUTO": "Auto"}
LIVEVIEW_OK = "Liveview should not be prohibited"
LIVEVIEW_BLOCKED = "Live View prohibit conditions: Exposure Program Mode is not P/A/S/M"
# In AUTO the D3500 reports a generic aperture list instead of the lens limits.
GENERIC_APERTURES = [
    "f/1", "f/1.1", "f/1.2", "f/1.4", "f/1.6", "f/1.8", "f/2", "f/2.2", "f/2.5", "f/2.8",
    "f/3.2",
]
FILE_TYPES = {"NEF (Raw)": ("NEF",), "NEF+Fine": ("JPG", "NEF")}
NEF_PLACEHOLDER = b"lensmind mock NEF: not a real raw file\n"


def parse_shutter(text: str) -> float:
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return float(numerator) / float(denominator)
    return float(text)


def parse_aperture(text: str) -> float:
    return float(text.removeprefix("f/"))


class MockCamera:
    def __init__(self, dial: str = "M", lang: str = "it") -> None:
        groups = load_catalog()
        self._lang = lang
        self._layout = [(g.name, g.label, [s.name for s in g.settings]) for g in groups]
        self._settings = {s.name: s for g in groups for s in g.settings}
        self._lens_apertures = list(self._settings["f-number"].choices or [])
        self._dial = "M"
        self._liveview = False
        self._counter = 0
        self._fail_next = False
        self._closed = False
        self.turn_dial(dial)

    # Mock-only hooks -----------------------------------------------------------

    def turn_dial(self, mode: str) -> None:
        if mode not in DIAL_MODES:
            raise ValueError(f"dial must be one of {DIAL_MODES}, not {mode!r}")
        self._dial = mode
        for name, readonly in READONLY_BY_DIAL[mode].items():
            self._replace(name, readonly=readonly)
        self._replace("expprogram", value=EXPPROGRAM[mode])
        apertures = GENERIC_APERTURES + self._lens_apertures if mode == "AUTO" else self._lens_apertures
        self._replace("f-number", choices=list(apertures))
        self._replace("liveviewprohibit", value=LIVEVIEW_BLOCKED if mode == "AUTO" else LIVEVIEW_OK)
        if mode == "AUTO":
            self._liveview = False
        self._auto_expose()

    def simulate_disconnect(self) -> None:
        self._fail_next = True

    def exposure_error(self) -> float:
        """Stops above (positive) or below the correct exposure for the scene."""
        return self._error(
            parse_shutter(str(self._value("shutterspeed2"))),
            parse_aperture(str(self._value("f-number"))),
        )

    @property
    def closed(self) -> bool:
        return self._closed

    # Camera protocol -----------------------------------------------------------

    def status(self) -> CameraStatus:
        self._check()
        return CameraStatus(
            manufacturer=str(self._value("manufacturer")),
            model=str(self._value("cameramodel")),
            battery=str(self._value("batterylevel")),
            can_preview=True,
            liveview_active=self._liveview,
            liveview_blocked_reason=liveview_block_reason(str(self._value("liveviewprohibit"))),
        )

    def settings(self) -> list[SettingGroup]:
        self._check()
        return [
            SettingGroup(name, label, [self._settings[n] for n in names])
            for name, label, names in self._layout
        ]

    def set(self, name: str, value: SettingValue) -> Setting:
        self._check()
        coerced = validate(self._settings.get(name), name, value, self._lang)
        self._replace(name, value=coerced)
        if name in ("shutterspeed", "shutterspeed2"):
            self._set_shutter_index((self._settings[name].choices or []).index(str(coerced)))
        self._auto_expose()
        return self._settings[name]

    def capture(self) -> list[CapturedFile]:
        self._check()
        self._liveview = False
        self._counter += 1
        stem = f"DSC_{self._counter:04d}"
        files = []
        for extension in FILE_TYPES.get(str(self._value("imagequality")), ("JPG",)):
            data = render(self.exposure_error(), CAPTURE_SIZE) if extension == "JPG" else NEF_PLACEHOLDER
            files.append(CapturedFile(f"{stem}.{extension}", data))
        return files

    def preview(self) -> bytes:
        self._check()
        reason = liveview_block_reason(str(self._value("liveviewprohibit")))
        if reason:
            raise CameraError(reason, 409)
        self._liveview = True
        return render(self.exposure_error(), PREVIEW_SIZE)

    def end_liveview(self) -> None:
        self._check()
        self._liveview = False

    def close(self) -> None:
        self._closed = True

    # Internals -----------------------------------------------------------------

    def _check(self) -> None:
        if self._fail_next:
            self._fail_next = False
            raise CameraDisconnected(msg(self._lang, "not_connected"), 503)

    def _value(self, name: str) -> SettingValue:
        return self._settings[name].value

    def _replace(self, name: str, **changes: object) -> None:
        self._settings[name] = replace(self._settings[name], **changes)

    def _error(self, seconds: float, aperture: float) -> float:
        iso = float(self._value("iso"))
        return SCENE_EV100 + math.log2(seconds * iso / 100 / aperture**2)

    def _set_shutter_index(self, index: int) -> None:
        for name in ("shutterspeed2", "shutterspeed"):
            self._replace(name, value=(self._settings[name].choices or [])[index])

    def _auto_expose(self) -> None:
        """In A and AUTO the camera chooses what the dial does not leave to the user."""
        if self._dial == "M":
            return
        target = float(self._value("exposurecompensation"))
        times = self._settings["shutterspeed2"].choices or []
        apertures = [str(self._value("f-number"))] if self._dial == "A" else self._lens_apertures
        _, _, index, aperture = min(
            (
                abs(self._error(parse_shutter(t), parse_aperture(a)) - target),
                abs(math.log2(parse_aperture(a) / 5.6)),
                i,
                a,
            )
            for i, t in enumerate(times)
            for a in apertures
        )
        self._set_shutter_index(index)
        self._replace("f-number", value=aperture)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_mock.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera/mock.py tests/test_mock.py
git commit -m "$(printf 'Add simulated D3500 with dial and exposure model\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 6: CameraSession

**Files:**
- Create: `src/lensmind/camera/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `Camera`, `CameraError`, `CameraDisconnected` (Task 2); `MockCamera` in tests (Task 5).
- Produces: `CameraSession(factory: Callable[[], Camera], idle_seconds: float = 5.0, clock: Callable[[], float] = time.monotonic, watchdog_interval: float = 1.0)` implementing `Camera`, plus `start_watchdog() -> None` and `check_idle() -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_session.py`:
```python
import threading
import time

import pytest

from lensmind.camera.base import CameraDisconnected, CameraError, CameraStatus
from lensmind.camera.mock import MockCamera
from lensmind.camera.session import CameraSession


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class RecordingCamera(MockCamera):
    def __init__(self) -> None:
        super().__init__(lang="en")
        self.calls: list[str] = []

    def preview(self) -> bytes:
        self.calls.append("preview")
        return super().preview()

    def end_liveview(self) -> None:
        self.calls.append("end_liveview")
        super().end_liveview()

    def capture(self):  # type: ignore[no-untyped-def]
        self.calls.append("capture")
        return super().capture()


def make_session(clock: Clock | None = None) -> tuple[CameraSession, list[RecordingCamera]]:
    created: list[RecordingCamera] = []

    def factory() -> RecordingCamera:
        camera = RecordingCamera()
        created.append(camera)
        return camera

    return CameraSession(factory, idle_seconds=5, clock=clock or Clock()), created


def test_connects_lazily_and_once() -> None:
    session, created = make_session()
    assert created == []
    session.status()
    session.settings()
    assert len(created) == 1


def test_reconnects_after_disconnect() -> None:
    session, created = make_session()
    session.status()
    created[0].simulate_disconnect()
    with pytest.raises(CameraDisconnected):
        session.status()
    assert created[0].closed
    assert session.status().model == "D3500"
    assert len(created) == 2


def test_soft_error_keeps_connection() -> None:
    session, created = make_session()
    with pytest.raises(CameraError) as caught:
        session.set("iso", "123")
    assert caught.value.status == 422
    session.status()
    assert len(created) == 1


def test_factory_failure_is_reported_then_retried() -> None:
    attempts: list[int] = []

    def flaky() -> MockCamera:
        attempts.append(1)
        if len(attempts) == 1:
            raise CameraDisconnected("Camera not connected", 503)
        return MockCamera(lang="en")

    session = CameraSession(flaky, idle_seconds=5)
    with pytest.raises(CameraDisconnected):
        session.status()
    assert session.status().model == "D3500"


def test_capture_ends_liveview_first() -> None:
    session, created = make_session()
    session.preview()
    session.capture()
    assert created[0].calls == ["preview", "end_liveview", "capture"]


def test_preview_after_capture_restarts_liveview() -> None:
    session, created = make_session()
    session.preview()
    files = session.capture()
    assert files
    assert session.preview()[:2] == b"\xff\xd8"
    assert created[0].status().liveview_active


def test_watchdog_stops_idle_liveview() -> None:
    clock = Clock()
    session, created = make_session(clock)
    session.preview()
    clock.now = 4.0
    session.check_idle()
    assert created[0].status().liveview_active
    clock.now = 5.1
    session.check_idle()
    assert not created[0].status().liveview_active


def test_watchdog_does_not_connect_an_idle_session() -> None:
    session, created = make_session()
    session.check_idle()
    assert created == []


def test_calls_are_serialised() -> None:
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    class SlowCamera(MockCamera):
        def status(self) -> CameraStatus:
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.01)
            with guard:
                state["active"] -= 1
            return super().status()

    session = CameraSession(lambda: SlowCamera(lang="en"), idle_seconds=5)
    threads = [threading.Thread(target=session.status) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert state["peak"] == 1


def test_watchdog_thread_runs_and_stops() -> None:
    clock = Clock()
    camera = MockCamera(lang="en")
    session = CameraSession(lambda: camera, idle_seconds=1, clock=clock, watchdog_interval=0.01)
    session.preview()
    clock.now = 2.0
    session.start_watchdog()
    deadline = time.monotonic() + 2
    while camera.status().liveview_active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not camera.status().liveview_active
    session.close()
    assert camera.closed
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_session.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.camera.session'`

- [ ] **Step 3: Write `camera/session.py`**

```python
"""One camera, one command at a time: locking, lazy reconnection, idle live view."""

import logging
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from lensmind.camera.base import (
    Camera,
    CameraDisconnected,
    CameraError,
    CameraStatus,
    CapturedFile,
    Setting,
    SettingGroup,
    SettingValue,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CameraSession:
    """Implements `Camera` on top of a camera created on demand by `factory`."""

    def __init__(
        self,
        factory: Callable[[], Camera],
        idle_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        watchdog_interval: float = 1.0,
    ) -> None:
        self._factory = factory
        self._idle_seconds = idle_seconds
        self._clock = clock
        self._interval = watchdog_interval
        self._lock = threading.RLock()
        self._camera: Camera | None = None
        self._liveview = False
        self._last_preview = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # Watchdog ------------------------------------------------------------------

    def start_watchdog(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._watch, name="liveview-watchdog", daemon=True)
            self._thread.start()

    def _watch(self) -> None:
        while not self._stop.wait(self._interval):
            self.check_idle()

    def check_idle(self) -> None:
        """Turn live view off when no preview was requested for `idle_seconds`."""
        with self._lock:
            if not self._liveview or self._clock() - self._last_preview <= self._idle_seconds:
                return
            try:
                self.end_liveview()
            except CameraError:
                logger.warning("could not stop idle live view", exc_info=True)

    # Camera protocol -----------------------------------------------------------

    def status(self) -> CameraStatus:
        return self._call(lambda camera: camera.status())

    def settings(self) -> list[SettingGroup]:
        return self._call(lambda camera: camera.settings())

    def set(self, name: str, value: SettingValue) -> Setting:
        return self._call(lambda camera: camera.set(name, value))

    def capture(self) -> list[CapturedFile]:
        with self._lock:
            if self._liveview:
                self.end_liveview()
            return self._call(lambda camera: camera.capture())

    def preview(self) -> bytes:
        with self._lock:
            frame = self._call(lambda camera: camera.preview())
            self._liveview = True
            self._last_preview = self._clock()
            return frame

    def end_liveview(self) -> None:
        with self._lock:
            if self._camera is not None:
                self._call(lambda camera: camera.end_liveview())
            self._liveview = False

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        with self._lock:
            if self._camera is not None:
                try:
                    self._camera.close()
                finally:
                    self._camera = None

    # Internals -----------------------------------------------------------------

    def _call(self, action: Callable[[Camera], T]) -> T:
        with self._lock:
            if self._camera is None:
                self._camera = self._factory()
            try:
                return action(self._camera)
            except CameraDisconnected:
                self._drop()
                raise

    def _drop(self) -> None:
        camera, self._camera = self._camera, None
        self._liveview = False
        if camera is not None:
            try:
                camera.close()
            except Exception:
                logger.debug("closing a disconnected camera failed", exc_info=True)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_session.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera/session.py tests/test_session.py
git commit -m "$(printf 'Add camera session with single lock, reconnection and live view watchdog\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 7: PhotoStore

**Files:**
- Create: `src/lensmind/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `CapturedFile` (Task 2); `render` (Task 4) in tests.
- Produces: `Shot(id: str, files: list[str], thumb: str | None)`; `PhotoStore(root: Path, clock: Callable[[], datetime] = datetime.now)` with `save(files: list[CapturedFile]) -> Shot`, `list_shots(limit: int = 50) -> list[Shot]`, `resolve(name: str) -> Path | None`, `thumb_path(name: str) -> Path | None`. `THUMB_SIZE = 400`.

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
from datetime import datetime
from pathlib import Path

from PIL import Image

from lensmind.camera.base import CapturedFile
from lensmind.camera.mock_image import render
from lensmind.storage import THUMB_SIZE, PhotoStore

JPEG = render(0.0, (900, 600))
WHEN = datetime(2026, 10, 7, 21, 1, 33)


def store_at(root: Path, *times: datetime) -> PhotoStore:
    moments = iter(times or (WHEN,) * 10)
    return PhotoStore(root, clock=lambda: next(moments))


def raw_plus_jpeg(number: int = 1) -> list[CapturedFile]:
    return [
        CapturedFile(f"DSC_{number:04d}.JPG", JPEG),
        CapturedFile(f"DSC_{number:04d}.NEF", b"raw"),
    ]


def test_save_prefixes_and_groups(tmp_path: Path) -> None:
    shot = store_at(tmp_path).save(raw_plus_jpeg())
    assert shot.id == "20261007-210133_DSC_0001"
    assert shot.files == ["20261007-210133_DSC_0001.JPG", "20261007-210133_DSC_0001.NEF"]
    assert shot.thumb == "20261007-210133_DSC_0001.JPG"
    assert (tmp_path / "20261007-210133_DSC_0001.NEF").read_bytes() == b"raw"


def test_thumbnail_is_a_small_jpeg(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    shot = store.save(raw_plus_jpeg())
    assert shot.thumb is not None
    thumb = store.thumb_path(shot.thumb)
    assert thumb is not None
    with Image.open(thumb) as image:
        assert max(image.size) <= THUMB_SIZE
    assert store.thumb_path(shot.files[1]) is None


def test_same_second_does_not_overwrite(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = store.save(raw_plus_jpeg(1))
    second = store.save(raw_plus_jpeg(1))
    assert first.id != second.id
    assert second.id == "20261007-210133-2_DSC_0001"
    assert len([p for p in tmp_path.iterdir() if p.is_file()]) == 4


def test_list_newest_first_with_limit(tmp_path: Path) -> None:
    store = store_at(tmp_path, datetime(2026, 1, 1, 10), datetime(2026, 1, 1, 11), datetime(2026, 1, 1, 12))
    for number in (1, 2, 3):
        store.save(raw_plus_jpeg(number))
    shots = store.list_shots(limit=2)
    assert [shot.id for shot in shots] == ["20260101-120000_DSC_0003", "20260101-110000_DSC_0002"]
    assert shots[0].thumb == "20260101-120000_DSC_0003.JPG"


def test_list_ignores_hidden_and_tolerates_foreign_files(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    store.save(raw_plus_jpeg())
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    (tmp_path / "notes.txt").write_text("hello")
    shots = store.list_shots()
    ids = {shot.id for shot in shots}
    assert ids == {"20261007-210133_DSC_0001", "notes"}
    assert next(shot for shot in shots if shot.id == "notes").thumb is None


def test_resolve_rejects_unsafe_or_missing_names(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    shot = store.save(raw_plus_jpeg())
    assert store.resolve(shot.files[0]) == tmp_path / shot.files[0]
    for name in ["../etc/passwd", "..", ".thumbs", "a/b", "a\\b", "missing.jpg", ""]:
        assert store.resolve(name) is None


def test_camera_folders_are_stripped_from_names(tmp_path: Path) -> None:
    shot = store_at(tmp_path).save([CapturedFile("/store/DCIM/../DSC_0009.JPG", JPEG)])
    assert shot.files == ["20261007-210133_DSC_0009.JPG"]
    assert (tmp_path / "20261007-210133_DSC_0009.JPG").is_file()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_storage.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.storage'`

- [ ] **Step 3: Write `storage.py`**

```python
"""Saving downloaded shots on the Pi, listing them and serving them safely."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from lensmind.camera.base import CapturedFile

THUMB_SIZE = 400
THUMB_DIR = ".thumbs"
IMAGE_SUFFIXES = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class Shot:
    id: str
    files: list[str]
    thumb: str | None


class PhotoStore:
    def __init__(self, root: Path, clock: Callable[[], datetime] = datetime.now) -> None:
        self.root = root
        self._thumbs = root / THUMB_DIR
        self._thumbs.mkdir(parents=True, exist_ok=True)
        self._clock = clock

    def save(self, files: list[CapturedFile]) -> Shot:
        base_names = [_safe_name(f.name) for f in files]
        prefix = self._free_prefix(base_names)
        names = []
        for captured, base_name in zip(files, base_names, strict=True):
            name = f"{prefix}_{base_name}"
            (self.root / name).write_bytes(captured.data)
            if Path(name).suffix.lower() in IMAGE_SUFFIXES:
                self._make_thumb(name)
            names.append(name)
        return self._shot(Path(names[0]).stem, names)

    def list_shots(self, limit: int = 50) -> list[Shot]:
        groups: dict[str, list[Path]] = {}
        for path in self.root.iterdir():
            if path.name.startswith(".") or not path.is_file():
                continue
            groups.setdefault(path.stem, []).append(path)

        def newest(item: tuple[str, list[Path]]) -> tuple[int, str]:
            stem, paths = item
            return max(p.stat().st_mtime_ns for p in paths), stem

        ordered = sorted(groups.items(), key=newest, reverse=True)[:limit]
        return [self._shot(stem, sorted(p.name for p in paths)) for stem, paths in ordered]

    def resolve(self, name: str) -> Path | None:
        if not _is_plain_name(name):
            return None
        path = self.root / name
        return path if path.is_file() else None

    def thumb_path(self, name: str) -> Path | None:
        if self.resolve(name) is None:
            return None
        path = self._thumbs / f"{name}.jpg"
        return path if path.is_file() else None

    def _free_prefix(self, base_names: list[str]) -> str:
        stamp = self._clock().strftime("%Y%m%d-%H%M%S")
        prefix, attempt = stamp, 1
        while any((self.root / f"{prefix}_{name}").exists() for name in base_names):
            attempt += 1
            prefix = f"{stamp}-{attempt}"
        return prefix

    def _shot(self, stem: str, names: list[str]) -> Shot:
        thumb = next((n for n in names if (self._thumbs / f"{n}.jpg").is_file()), None)
        return Shot(id=stem, files=names, thumb=thumb)

    def _make_thumb(self, name: str) -> None:
        try:
            with Image.open(self.root / name) as image:
                image.draft("RGB", (THUMB_SIZE, THUMB_SIZE))
                thumb = image.convert("RGB")
                thumb.thumbnail((THUMB_SIZE, THUMB_SIZE))
                thumb.save(self._thumbs / f"{name}.jpg", "JPEG", quality=80)
        except (OSError, Image.DecompressionBombError):
            pass  # the original is kept; the gallery shows it without a thumbnail


def _safe_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1].lstrip(".")
    return base or "file"


def _is_plain_name(name: str) -> bool:
    return bool(name) and not name.startswith(".") and "/" not in name and "\\" not in name
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_storage.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/storage.py tests/test_storage.py
git commit -m "$(printf 'Store shots with timestamped names and thumbnails\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 8: Settings, HTTP API and entry point

**Files:**
- Create: `src/lensmind/settings.py`, `src/lensmind/api/messages.py`, `src/lensmind/api/schemas.py`, `src/lensmind/api/routes_camera.py`, `src/lensmind/api/app.py`, `src/lensmind/__main__.py`, `web/index.html` (placeholder, replaced in Task 10)
- Test: `tests/test_settings.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: everything from Tasks 2–7. `lensmind.camera.gphoto.GPhotoCamera(lang)` is imported lazily and only when `mock` is false; it is written in Task 9.
- Produces: `Settings` dataclass (`mock, mock_dial, host, port, language, photos_dir, liveview_idle_seconds`) with `Settings.from_env(env: Mapping[str, str] | None = None)`; `create_app(settings: Settings | None = None, camera_factory: Callable[[], Camera] | None = None, web_dir: Path = WEB_DIR) -> FastAPI`; `main()` in `lensmind.__main__`. JSON shapes: `SettingOut`, `GroupOut`, `SettingsOut {groups, primary}`, `StatusOut {connected, detail, language, camera}`, `ShotOut {id, files: [{name, url}], thumb_url}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_settings.py`:
```python
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
    "env", [{"LENSMIND_LANGUAGE": "fr"}, {"LENSMIND_MOCK_DIAL": "S"}, {"LENSMIND_PORT": "eighty"}]
)
def test_rejects_invalid_values(env: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(env)
```

`tests/test_api.py`:
```python
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lensmind.api.app import create_app
from lensmind.camera.base import CameraDisconnected
from lensmind.camera.mock import MockCamera
from lensmind.settings import Settings


def settings_for(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(mock=True, language="en", photos_dir=tmp_path, **overrides)  # type: ignore[arg-type]


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
            "connected": False, "detail": "Camera not connected", "language": "en", "camera": None,
        }
        assert test_client.get("/api/settings").status_code == 503


def test_settings_and_primary(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert [g["name"] for g in body["groups"]] == ["settings", "status", "imgsettings", "capturesettings"]
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
    for name, value in [("burstnumber", 3), ("fastfs", False), ("artist", "M"), ("datetime", 1800000000)]:
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_settings.py tests/test_api.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.settings'`

- [ ] **Step 3: Write `settings.py`**

```python
"""Configuration from LENSMIND_* environment variables."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGES = ("it", "en")
DIAL_MODES = ("M", "A", "AUTO")


def _default_photos_dir() -> Path:
    return Path("~/lensmind-photos").expanduser()


@dataclass(frozen=True)
class Settings:
    mock: bool = False
    mock_dial: str = "M"
    host: str = "0.0.0.0"
    port: int = 8000
    language: str = "it"
    photos_dir: Path = field(default_factory=_default_photos_dir)
    liveview_idle_seconds: float = 5.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        language = env.get("LENSMIND_LANGUAGE", "it").lower()
        if language not in LANGUAGES:
            raise ValueError(f"LENSMIND_LANGUAGE must be one of {LANGUAGES}, not {language!r}")
        dial = env.get("LENSMIND_MOCK_DIAL", "M").upper()
        if dial not in DIAL_MODES:
            raise ValueError(f"LENSMIND_MOCK_DIAL must be one of {DIAL_MODES}, not {dial!r}")
        photos_dir = env.get("LENSMIND_PHOTOS_DIR")
        return cls(
            mock=env.get("LENSMIND_MOCK", "0").strip().lower() in {"1", "true", "yes", "on"},
            mock_dial=dial,
            host=env.get("LENSMIND_HOST", "0.0.0.0"),
            port=int(env.get("LENSMIND_PORT", "8000")),
            language=language,
            photos_dir=Path(photos_dir).expanduser() if photos_dir else _default_photos_dir(),
            liveview_idle_seconds=float(env.get("LENSMIND_LIVEVIEW_IDLE_SECONDS", "5")),
        )
```

- [ ] **Step 4: Write `api/messages.py`**

```python
"""User-facing messages of the API layer, per language."""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {"photo_not_found": "Foto non trovata: {name}"},
    "en": {"photo_not_found": "Photo not found: {name}"},
}


def msg(lang: str, key: str, **params: object) -> str:
    return MESSAGES.get(lang, MESSAGES["en"])[key].format(**params)
```

- [ ] **Step 5: Write `api/schemas.py`**

```python
"""JSON request and response models."""

from dataclasses import asdict
from typing import Self
from urllib.parse import quote

from pydantic import BaseModel

from lensmind.camera.base import CameraStatus, Setting, SettingGroup
from lensmind.storage import Shot


class SettingOut(BaseModel):
    name: str
    label: str
    type: str
    value: int | float | str
    readonly: bool
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None

    @classmethod
    def from_model(cls, setting: Setting) -> Self:
        return cls(**asdict(setting))


class GroupOut(BaseModel):
    name: str
    label: str
    settings: list[SettingOut]

    @classmethod
    def from_model(cls, group: SettingGroup) -> Self:
        return cls(
            name=group.name,
            label=group.label,
            settings=[SettingOut.from_model(s) for s in group.settings],
        )


class SettingsOut(BaseModel):
    groups: list[GroupOut]
    primary: dict[str, str]


class SetValueIn(BaseModel):
    value: bool | int | float | str


class CameraStatusOut(BaseModel):
    manufacturer: str
    model: str
    battery: str | None
    can_preview: bool
    liveview_active: bool
    liveview_blocked_reason: str | None

    @classmethod
    def from_model(cls, status: CameraStatus) -> Self:
        return cls(**asdict(status))


class StatusOut(BaseModel):
    connected: bool
    detail: str | None = None
    language: str
    camera: CameraStatusOut | None = None


class FileOut(BaseModel):
    name: str
    url: str


class ShotOut(BaseModel):
    id: str
    files: list[FileOut]
    thumb_url: str | None

    @classmethod
    def from_shot(cls, shot: Shot) -> Self:
        return cls(
            id=shot.id,
            files=[FileOut(name=n, url=f"/api/photos/{quote(n)}") for n in shot.files],
            thumb_url=f"/api/photos/{quote(shot.thumb)}/thumb" if shot.thumb else None,
        )
```

- [ ] **Step 6: Write `api/routes_camera.py`**

```python
"""Camera, live view and photo endpoints. Sync: FastAPI runs them in its thread pool."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from lensmind.api.messages import msg
from lensmind.api.schemas import (
    CameraStatusOut,
    GroupOut,
    SettingOut,
    SettingsOut,
    SetValueIn,
    ShotOut,
    StatusOut,
)
from lensmind.camera.base import CameraError
from lensmind.camera.primary import resolve_primary
from lensmind.camera.session import CameraSession
from lensmind.storage import PhotoStore

router = APIRouter(prefix="/api")


def _session(request: Request) -> CameraSession:
    return request.app.state.session


def _store(request: Request) -> PhotoStore:
    return request.app.state.store


def _language(request: Request) -> str:
    return request.app.state.settings.language


@router.get("/status")
def get_status(request: Request) -> StatusOut:
    try:
        status = _session(request).status()
    except CameraError as error:
        return StatusOut(connected=False, detail=error.message, language=_language(request))
    return StatusOut(
        connected=True, language=_language(request), camera=CameraStatusOut.from_model(status)
    )


@router.get("/settings")
def get_settings(request: Request) -> SettingsOut:
    groups = _session(request).settings()
    return SettingsOut(
        groups=[GroupOut.from_model(g) for g in groups], primary=resolve_primary(groups)
    )


@router.put("/settings/{name}")
def put_setting(name: str, body: SetValueIn, request: Request) -> SettingOut:
    return SettingOut.from_model(_session(request).set(name, body.value))


@router.post("/capture")
def capture(request: Request) -> ShotOut:
    files = _session(request).capture()
    return ShotOut.from_shot(_store(request).save(files))


@router.get("/preview")
def preview(request: Request) -> Response:
    frame = _session(request).preview()
    return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/liveview/stop", status_code=204)
def stop_liveview(request: Request) -> Response:
    _session(request).end_liveview()
    return Response(status_code=204)


@router.get("/photos")
def list_photos(request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[ShotOut]:
    return [ShotOut.from_shot(shot) for shot in _store(request).list_shots(limit)]


@router.get("/photos/{name}")
def get_photo(name: str, request: Request) -> FileResponse:
    path = _store(request).resolve(name)
    if path is None:
        raise HTTPException(404, detail=msg(_language(request), "photo_not_found", name=name))
    return FileResponse(path)


@router.get("/photos/{name}/thumb")
def get_thumb(name: str, request: Request) -> FileResponse:
    path = _store(request).thumb_path(name)
    if path is None:
        raise HTTPException(404, detail=msg(_language(request), "photo_not_found", name=name))
    return FileResponse(path, media_type="image/jpeg")
```

- [ ] **Step 7: Write `api/app.py`**

```python
"""FastAPI application: lifespan, error mapping, routes and the static web app."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lensmind.api.routes_camera import router as camera_router
from lensmind.camera.base import Camera, CameraError
from lensmind.camera.session import CameraSession
from lensmind.settings import Settings
from lensmind.storage import PhotoStore

# src/lensmind/api/app.py -> repository root -> web/ (the package is installed editable).
WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def camera_factory_for(settings: Settings) -> Callable[[], Camera]:
    if settings.mock:
        from lensmind.camera.mock import MockCamera

        return lambda: MockCamera(dial=settings.mock_dial, lang=settings.language)
    from lensmind.camera.gphoto import GPhotoCamera

    return lambda: GPhotoCamera(lang=settings.language)


async def camera_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CameraError)
    return JSONResponse(status_code=error.status, content={"detail": error.message})


def create_app(
    settings: Settings | None = None,
    camera_factory: Callable[[], Camera] | None = None,
    web_dir: Path = WEB_DIR,
) -> FastAPI:
    config = settings or Settings.from_env()
    factory = camera_factory or camera_factory_for(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session = CameraSession(factory, idle_seconds=config.liveview_idle_seconds)
        session.start_watchdog()
        app.state.settings = config
        app.state.session = session
        app.state.store = PhotoStore(config.photos_dir)
        try:
            yield
        finally:
            session.close()

    app = FastAPI(title="lensmind", lifespan=lifespan)
    app.add_exception_handler(CameraError, camera_error_handler)
    app.include_router(camera_router)
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
```

- [ ] **Step 8: Write `__main__.py` and the placeholder page**

`src/lensmind/__main__.py`:
```python
"""`lensmind` command: run the server with configuration from the environment."""

import uvicorn

from lensmind.api.app import create_app
from lensmind.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

`web/index.html` (placeholder until Task 10):
```html
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>lensmind</title></head>
<body><p>lensmind</p></body>
</html>
```

Add to `tests/test_settings.py`:
```python
def test_main_runs_uvicorn_with_configured_address(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import uvicorn

    from lensmind.__main__ import main

    calls: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: calls.update(host=host, port=port))
    monkeypatch.setenv("LENSMIND_MOCK", "1")
    monkeypatch.setenv("LENSMIND_PORT", "8123")
    monkeypatch.setenv("LENSMIND_PHOTOS_DIR", str(tmp_path))
    main()
    assert calls == {"host": "0.0.0.0", "port": 8123}
```

- [ ] **Step 9: Run the tests**

Run: `pytest -q`
Expected: all pass. If `test_put_wrong_json_type_is_422` fails because `iso` received `400` as a string, check that `SetValueIn.value` lists `bool | int | float | str` in that order (Pydantic smart unions keep the exact JSON type).

- [ ] **Step 10: Try it by hand**

```bash
LENSMIND_MOCK=1 LENSMIND_PHOTOS_DIR=./photos lensmind &
sleep 2
curl -s localhost:8000/api/status
curl -s -X PUT localhost:8000/api/settings/iso -H 'content-type: application/json' -d '{"value":"400"}'
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' localhost:8000/api/preview
kill %1
```
Expected: status JSON with `"connected":true`, the iso setting with `"value":"400"`, `200 image/jpeg`.

- [ ] **Step 11: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind tests/test_settings.py tests/test_api.py web/index.html
git commit -m "$(printf 'Add configuration, HTTP API and lensmind entry point\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 9: libgphoto2 camera

**Files:**
- Create: `src/lensmind/camera/gphoto.py`, `tests/fake_gphoto2.py`
- Test: `tests/test_gphoto.py`

**Interfaces:**
- Consumes: Task 2 models, `validate`, `liveview_block_reason`, `EXCLUDED_SECTIONS`, `msg`; `parse_dump` (Task 3) in the fake.
- Produces: `GPhotoCamera(lang: str = "it")` implementing `Camera`. Already referenced by `camera_factory_for` in Task 8.

python-gphoto2 calls used (object API): `gp.Camera()`, `.init()`, `.exit()`, `.get_abilities()` (`.operations`, `.model`), `.get_config()`, `.get_single_config(name)`, `.set_single_config(name, widget)`, `.capture(gp.GP_CAPTURE_IMAGE)` → path with `.folder`/`.name`, `.wait_for_event(timeout_ms)` → `(event_type, data)`, `.file_get(folder, name, gp.GP_FILE_TYPE_NORMAL)`, `.capture_preview()`, `CameraFile.get_data_and_size()`; widget `.get_name()`, `.get_label()`, `.get_type()`, `.get_value()`, `.set_value(v)`, `.get_readonly()`, `.count_children()`, `.get_child(i)`, `.count_choices()`, `.get_choice(i)`, `.get_range()`; `gp.GPhoto2Error` with `.code`.

- [ ] **Step 1: Write the fake `gphoto2` module**

`tests/fake_gphoto2.py`:
```python
"""In-memory stand-in for python-gphoto2, built from a real `--list-all-config` dump."""

import copy
from dataclasses import dataclass
from pathlib import Path

from lensmind.camera.dump import parse_dump

GP_OK = 0
GP_ERROR = -1
GP_ERROR_BAD_PARAMETERS = -2
GP_ERROR_NOT_SUPPORTED = -6
GP_ERROR_IO = -7
GP_ERROR_IO_USB_CLAIM = -53
GP_ERROR_MODEL_NOT_FOUND = -105
GP_ERROR_CAMERA_BUSY = -110

(
    GP_WIDGET_WINDOW,
    GP_WIDGET_SECTION,
    GP_WIDGET_TEXT,
    GP_WIDGET_RANGE,
    GP_WIDGET_TOGGLE,
    GP_WIDGET_RADIO,
    GP_WIDGET_MENU,
    GP_WIDGET_BUTTON,
    GP_WIDGET_DATE,
) = range(9)
GP_CAPTURE_IMAGE = 0
GP_FILE_TYPE_NORMAL = 1
GP_EVENT_UNKNOWN, GP_EVENT_TIMEOUT, GP_EVENT_FILE_ADDED = 0, 1, 2
GP_OPERATION_CONFIG = 1
GP_OPERATION_CAPTURE_PREVIEW = 8

_TYPES = {
    "WINDOW": GP_WIDGET_WINDOW,
    "SECTION": GP_WIDGET_SECTION,
    "TEXT": GP_WIDGET_TEXT,
    "RANGE": GP_WIDGET_RANGE,
    "TOGGLE": GP_WIDGET_TOGGLE,
    "RADIO": GP_WIDGET_RADIO,
    "MENU": GP_WIDGET_MENU,
    "BUTTON": GP_WIDGET_BUTTON,
    "DATE": GP_WIDGET_DATE,
}
_VALUE_TYPES = {
    GP_WIDGET_TEXT: str,
    GP_WIDGET_RADIO: str,
    GP_WIDGET_MENU: str,
    GP_WIDGET_RANGE: float,
    GP_WIDGET_TOGGLE: int,
    GP_WIDGET_DATE: int,
}

# Set by tests (via reset) before creating a Camera.
DUMP_PATH: Path | None = None
INIT_ERROR: int | None = None
last_camera: "Camera | None" = None


def reset(dump_path: Path) -> None:
    global DUMP_PATH, INIT_ERROR, last_camera
    DUMP_PATH, INIT_ERROR, last_camera = dump_path, None, None


class GPhoto2Error(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"[{code}] fake gphoto2 error")
        self.code = code


class CameraWidget:
    def __init__(
        self,
        name: str,
        label: str,
        type_: int,
        value: object = None,
        readonly: bool = False,
        choices: tuple[str, ...] = (),
        range_: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        self.name, self.label, self.type, self.value = name, label, type_, value
        self.readonly, self.choices, self.range = readonly, choices, range_
        self.children: list[CameraWidget] = []

    def get_name(self) -> str:
        return self.name

    def get_label(self) -> str:
        return self.label

    def get_type(self) -> int:
        return self.type

    def get_value(self) -> object:
        return self.value

    def set_value(self, value: object) -> None:
        expected = _VALUE_TYPES[self.type]
        if type(value) is not expected:
            raise TypeError(f"{self.name}: expected {expected.__name__}, got {type(value).__name__}")
        self.value = value

    def get_readonly(self) -> int:
        return int(self.readonly)

    def count_children(self) -> int:
        return len(self.children)

    def get_child(self, index: int) -> "CameraWidget":
        return self.children[index]

    def count_choices(self) -> int:
        return len(self.choices)

    def get_choice(self, index: int) -> str:
        return self.choices[index]

    def get_range(self) -> tuple[float, float, float]:
        return self.range


def _value(type_: int, current: str) -> object:
    if type_ == GP_WIDGET_RANGE:
        return float(current)
    if type_ in (GP_WIDGET_TOGGLE, GP_WIDGET_DATE):
        return int(current)
    return current


def build_tree(path: Path) -> CameraWidget:
    root = CameraWidget("main", "Camera and Driver Configuration", GP_WIDGET_WINDOW)
    sections: dict[str, CameraWidget] = {}
    for entry in parse_dump(path.read_text(encoding="utf-8")):
        section = sections.get(entry.section)
        if section is None:
            section = CameraWidget(entry.section, entry.section, GP_WIDGET_SECTION)
            sections[entry.section] = section
            root.children.append(section)
        type_ = _TYPES[entry.type]
        section.children.append(
            CameraWidget(
                entry.name, entry.label, type_, _value(type_, entry.current), entry.readonly,
                entry.choices, (entry.bottom or 0.0, entry.top or 0.0, entry.step or 0.0),
            )
        )
    return root


@dataclass
class CameraFilePath:
    folder: str
    name: str


class CameraFile:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def get_data_and_size(self) -> bytes:
        return self._data


@dataclass
class CameraAbilities:
    model: str = "Nikon DSC D3500"
    operations: int = GP_OPERATION_CONFIG | GP_OPERATION_CAPTURE_PREVIEW


class Camera:
    def __init__(self) -> None:
        global last_camera
        assert DUMP_PATH is not None, "call fake_gphoto2.reset(dump) first"
        self.root = build_tree(DUMP_PATH)
        self.log: list[tuple[object, ...]] = []
        self.fail_next: dict[str, int] = {}
        self.events: list[tuple[int, object]] = []
        self.abilities = CameraAbilities()
        last_camera = self

    def _call(self, method: str, *args: object) -> None:
        self.log.append((method, *args))
        code = self.fail_next.pop(method, None)
        if code is not None:
            raise GPhoto2Error(code)

    def init(self) -> None:
        self._call("init")
        if INIT_ERROR is not None:
            raise GPhoto2Error(INIT_ERROR)

    def exit(self) -> None:
        self._call("exit")

    def get_abilities(self) -> CameraAbilities:
        self._call("get_abilities")
        return self.abilities

    def get_config(self) -> CameraWidget:
        self._call("get_config")
        return self.root

    def get_single_config(self, name: str) -> CameraWidget:
        self._call("get_single_config", name)
        widget = self._find(self.root, name)
        if widget is None:
            raise GPhoto2Error(GP_ERROR_BAD_PARAMETERS)
        return copy.copy(widget)

    def set_single_config(self, name: str, widget: CameraWidget) -> None:
        self._call("set_single_config", name, widget.get_value())
        target = self._find(self.root, name)
        if target is None:
            raise GPhoto2Error(GP_ERROR_BAD_PARAMETERS)
        target.value = widget.get_value()

    def capture(self, kind: int) -> CameraFilePath:
        self._call("capture", kind)
        return CameraFilePath("/store_00010001/DCIM/100D3500", "DSC_0001.JPG")

    def wait_for_event(self, timeout_ms: int) -> tuple[int, object]:
        self._call("wait_for_event")
        return self.events.pop(0) if self.events else (GP_EVENT_TIMEOUT, None)

    def file_get(self, folder: str, name: str, kind: int) -> CameraFile:
        self._call("file_get", folder, name)
        return CameraFile(f"data:{name}".encode())

    def capture_preview(self) -> CameraFile:
        self._call("capture_preview")
        return CameraFile(b"\xff\xd8fake-preview\xff\xd9")

    def _find(self, widget: CameraWidget, name: str) -> CameraWidget | None:
        for child in widget.children:
            if child.type in (GP_WIDGET_WINDOW, GP_WIDGET_SECTION):
                found = self._find(child, name)
                if found is not None:
                    return found
            elif child.name == name:
                return child
        return None
```

- [ ] **Step 2: Write the failing tests**

`tests/test_gphoto.py`:
```python
import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import fake_gphoto2
import pytest

from lensmind.camera.base import CameraDisconnected, CameraError, Setting

DUMPS = Path(__file__).resolve().parents[1] / "docs" / "cameras" / "d3500"


@pytest.fixture
def gp(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    fake_gphoto2.reset(DUMPS / "d3500-config-M.txt")
    monkeypatch.setitem(sys.modules, "gphoto2", fake_gphoto2)
    yield fake_gphoto2


def use_dump(mode: str) -> None:
    fake_gphoto2.reset(DUMPS / f"d3500-config-{mode}.txt")


def open_camera():  # type: ignore[no-untyped-def]
    from lensmind.camera.gphoto import GPhotoCamera

    return GPhotoCamera(lang="en")


@pytest.fixture
def cam(gp: ModuleType):  # type: ignore[no-untyped-def]
    return open_camera()


def by_name(cam, name: str) -> Setting:  # type: ignore[no-untyped-def]
    return next(s for g in cam.settings() for s in g.settings if s.name == name)


def log() -> list[tuple[object, ...]]:
    assert fake_gphoto2.last_camera is not None
    return fake_gphoto2.last_camera.log


def test_module_does_not_import_gphoto2_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "gphoto2", raising=False)
    import lensmind.camera.gphoto as module

    importlib.reload(module)
    assert "gphoto2" not in sys.modules


def test_no_camera_is_a_disconnection(gp: ModuleType) -> None:
    gp.INIT_ERROR = gp.GP_ERROR_MODEL_NOT_FOUND
    with pytest.raises(CameraDisconnected) as caught:
        open_camera()
    assert caught.value.status == 503
    assert "not connected" in caught.value.message


def test_usb_claim_explains_the_cause(gp: ModuleType) -> None:
    gp.INIT_ERROR = gp.GP_ERROR_IO_USB_CLAIM
    with pytest.raises(CameraDisconnected) as caught:
        open_camera()
    assert "another process" in caught.value.message


def test_settings_exclude_actions_and_other(cam) -> None:  # type: ignore[no-untyped-def]
    groups = cam.settings()
    assert [g.name for g in groups] == ["settings", "status", "imgsettings", "capturesettings"]
    names = [s.name for g in groups for s in g.settings]
    assert len(names) == 50
    assert len(set(names)) == 50


def test_settings_types_and_values(cam) -> None:  # type: ignore[no-untyped-def]
    aperture = by_name(cam, "f-number")
    burst = by_name(cam, "burstnumber")
    assert aperture.type == "choice" and aperture.choices and aperture.choices[0] == "f/3.5"
    assert (burst.type, burst.min, burst.max, burst.step, burst.value) == ("range", 1, 100, 1, 1.0)
    assert by_name(cam, "fastfs").type == "toggle"
    assert isinstance(by_name(cam, "datetime").value, int)
    assert by_name(cam, "batterylevel").readonly


def test_set_writes_the_converted_value(cam) -> None:  # type: ignore[no-untyped-def]
    assert cam.set("burstnumber", 3).value == 3.0
    assert ("set_single_config", "burstnumber", 3.0) in log()
    assert cam.set("iso", "200").value == "200"


def test_set_rejects_value_outside_lens_range(cam) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CameraError) as caught:
        cam.set("f-number", "f/1.8")
    assert caught.value.status == 422
    assert "f/3.5" in caught.value.message
    assert not any(entry[0] == "set_single_config" for entry in log())


def test_set_reads_fresh_readonly_flags(gp: ModuleType) -> None:
    use_dump("AUTO")
    cam = open_camera()
    with pytest.raises(CameraError) as caught:
        cam.set("f-number", "f/5.6")
    assert caught.value.status == 409


@pytest.mark.parametrize("name", ["opcode", "viewfinder", "5007", "nope"])
def test_set_refuses_hidden_or_unknown_names(cam, name: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CameraError) as caught:
        cam.set(name, "1")
    assert caught.value.status == 404


@pytest.mark.parametrize(
    ("code", "status"),
    [("GP_ERROR_CAMERA_BUSY", 503), ("GP_ERROR_BAD_PARAMETERS", 422), ("GP_ERROR_NOT_SUPPORTED", 409), ("GP_ERROR", 500)],
)
def test_soft_errors_keep_the_connection(cam, gp: ModuleType, code: str, status: int) -> None:  # type: ignore[no-untyped-def]
    cam.settings()
    gp.last_camera.fail_next["set_single_config"] = getattr(gp, code)
    with pytest.raises(CameraError) as caught:
        cam.set("iso", "200")
    assert not isinstance(caught.value, CameraDisconnected)
    assert caught.value.status == status


def test_io_error_is_a_disconnection(cam, gp: ModuleType) -> None:  # type: ignore[no-untyped-def]
    gp.last_camera.fail_next["get_config"] = gp.GP_ERROR_IO
    with pytest.raises(CameraDisconnected):
        cam.settings()


def test_status(cam) -> None:  # type: ignore[no-untyped-def]
    status = cam.status()
    assert status.manufacturer == "Nikon Corporation"
    assert status.model == "D3500"
    assert status.battery == "20%"
    assert status.can_preview
    assert status.liveview_blocked_reason is None


def test_status_reports_liveview_block_in_auto(gp: ModuleType) -> None:
    use_dump("AUTO")
    reason = open_camera().status().liveview_blocked_reason
    assert reason is not None and "P/A/S/M" in reason


def test_preview_refused_in_auto(gp: ModuleType) -> None:
    use_dump("AUTO")
    cam = open_camera()
    with pytest.raises(CameraError) as caught:
        cam.preview()
    assert caught.value.status == 409
    assert ("capture_preview",) not in log()


def test_preview_returns_a_frame(cam) -> None:  # type: ignore[no-untyped-def]
    assert cam.preview()[:2] == b"\xff\xd8"
    assert cam.status().liveview_active


def test_end_liveview_turns_viewfinder_off(cam) -> None:  # type: ignore[no-untyped-def]
    cam.preview()
    cam.end_liveview()
    assert ("set_single_config", "viewfinder", 0) in log()
    assert not cam.status().liveview_active


def test_capture_turns_viewfinder_off_first_and_collects_raw(cam, gp: ModuleType) -> None:  # type: ignore[no-untyped-def]
    gp.last_camera.events = [
        (gp.GP_EVENT_FILE_ADDED, gp.CameraFilePath("/store_00010001/DCIM/100D3500", "DSC_0001.NEF"))
    ]
    files = cam.capture()
    assert [f.name for f in files] == ["DSC_0001.JPG", "DSC_0001.NEF"]
    assert files[0].data == b"data:DSC_0001.JPG"
    entries = log()
    assert entries.index(("set_single_config", "viewfinder", 0)) < entries.index(
        ("capture", gp.GP_CAPTURE_IMAGE)
    )


def test_close_swallows_errors(cam, gp: ModuleType) -> None:  # type: ignore[no-untyped-def]
    gp.last_camera.fail_next["exit"] = gp.GP_ERROR_IO
    cam.close()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/test_gphoto.py -q`
Expected: `ModuleNotFoundError: No module named 'lensmind.camera.gphoto'`

- [ ] **Step 4: Write `camera/gphoto.py`**

```python
"""Camera implementation on libgphoto2 (python-gphoto2). The only gphoto2 importer."""

import time
from collections.abc import Callable
from typing import Any, TypeVar

from lensmind.camera.base import (
    EXCLUDED_SECTIONS,
    CameraDisconnected,
    CameraError,
    CameraStatus,
    CapturedFile,
    Setting,
    SettingGroup,
    SettingType,
    SettingValue,
    liveview_block_reason,
    validate,
)
from lensmind.camera.messages import msg

T = TypeVar("T")
# After capture, a RAW+JPEG second file arrives as GP_EVENT_FILE_ADDED.
SECOND_FILE_WAIT_SECONDS = 1.5


class GPhotoCamera:
    def __init__(self, lang: str = "it") -> None:
        import gphoto2 as gp  # lazy: mock mode must work without libgphoto2

        self._gp: Any = gp
        self._lang = lang
        self._types: dict[int, SettingType] = {
            gp.GP_WIDGET_RADIO: "choice",
            gp.GP_WIDGET_MENU: "choice",
            gp.GP_WIDGET_RANGE: "range",
            gp.GP_WIDGET_TOGGLE: "toggle",
            gp.GP_WIDGET_TEXT: "text",
            gp.GP_WIDGET_DATE: "date",
        }
        self._containers = {gp.GP_WIDGET_WINDOW, gp.GP_WIDGET_SECTION}
        self._liveview = False
        self._exposed: set[str] | None = None
        self._camera = gp.Camera()
        self._run(self._camera.init)

    # Camera protocol -----------------------------------------------------------

    def status(self) -> CameraStatus:
        abilities = self._run(self._camera.get_abilities)
        return CameraStatus(
            manufacturer=self._text("manufacturer") or "",
            model=self._text("cameramodel") or abilities.model,
            battery=self._text("batterylevel"),
            can_preview=bool(abilities.operations & self._gp.GP_OPERATION_CAPTURE_PREVIEW),
            liveview_active=self._liveview,
            liveview_blocked_reason=liveview_block_reason(self._text("liveviewprohibit")),
        )

    def settings(self) -> list[SettingGroup]:
        root = self._run(self._camera.get_config)
        groups: list[SettingGroup] = []
        seen: set[str] = set()
        for index in range(root.count_children()):
            section = root.get_child(index)
            if section.get_name() in EXCLUDED_SECTIONS:
                continue
            items: list[Setting] = []
            self._collect(section, items, seen)
            if items:
                groups.append(SettingGroup(section.get_name(), section.get_label(), items))
        self._exposed = seen
        return groups

    def set(self, name: str, value: SettingValue) -> Setting:
        if self._exposed is None:
            self.settings()
        assert self._exposed is not None
        widget = self._run(self._camera.get_single_config, name) if name in self._exposed else None
        # Re-read the widget: read-only flags and choices change with the dial and lens.
        current = self._to_setting(widget) if widget is not None else None
        coerced = validate(current, name, value, self._lang)
        self._run(widget.set_value, coerced)
        self._run(self._camera.set_single_config, name, widget)
        fresh = self._to_setting(self._run(self._camera.get_single_config, name))
        assert fresh is not None
        return fresh

    def capture(self) -> list[CapturedFile]:
        gp = self._gp
        self.end_liveview()
        first = self._run(self._camera.capture, gp.GP_CAPTURE_IMAGE)
        paths = [(first.folder, first.name)]
        deadline = time.monotonic() + SECOND_FILE_WAIT_SECONDS
        while (remaining := deadline - time.monotonic()) > 0:
            event, data = self._run(self._camera.wait_for_event, max(1, int(remaining * 1000)))
            if event == gp.GP_EVENT_FILE_ADDED:
                paths.append((data.folder, data.name))
            elif event == gp.GP_EVENT_TIMEOUT:
                break
        files = []
        for folder, name in paths:
            camera_file = self._run(self._camera.file_get, folder, name, gp.GP_FILE_TYPE_NORMAL)
            data = bytes(memoryview(self._run(camera_file.get_data_and_size)))
            files.append(CapturedFile(name, data))
        return files

    def preview(self) -> bytes:
        if not self._liveview:
            reason = liveview_block_reason(self._text("liveviewprohibit"))
            if reason:
                raise CameraError(reason, 409)
        camera_file = self._run(self._camera.capture_preview)
        self._liveview = True
        return bytes(memoryview(self._run(camera_file.get_data_and_size)))

    def end_liveview(self) -> None:
        widget = self._single("viewfinder")
        if widget is not None:
            self._run(widget.set_value, 0)
            self._run(self._camera.set_single_config, "viewfinder", widget)
        self._liveview = False

    def close(self) -> None:
        try:
            self._camera.exit()
        except self._gp.GPhoto2Error:
            pass

    # Internals -----------------------------------------------------------------

    def _run(self, function: Callable[..., T], *args: object) -> T:
        try:
            return function(*args)
        except self._gp.GPhoto2Error as error:
            raise self._translate(error) from error

    def _translate(self, error: Any) -> CameraError:
        gp, lang, code = self._gp, self._lang, error.code
        if code == gp.GP_ERROR_BAD_PARAMETERS:
            return CameraError(msg(lang, "bad_parameters"), 422)
        if code == gp.GP_ERROR_NOT_SUPPORTED:
            return CameraError(msg(lang, "not_supported"), 409)
        if code == gp.GP_ERROR_CAMERA_BUSY:
            return CameraError(msg(lang, "camera_busy"), 503)
        if code == gp.GP_ERROR:
            return CameraError(msg(lang, "camera_error", error=error), 500)
        if code == gp.GP_ERROR_MODEL_NOT_FOUND:
            return CameraDisconnected(msg(lang, "not_connected"), 503)
        if code == gp.GP_ERROR_IO_USB_CLAIM:
            return CameraDisconnected(msg(lang, "usb_claimed"), 503)
        return CameraDisconnected(msg(lang, "io_error", error=error), 503)

    def _single(self, name: str) -> Any | None:
        """The widget called `name`, or None when the camera does not have it."""
        gp = self._gp
        try:
            return self._camera.get_single_config(name)
        except gp.GPhoto2Error as error:
            if error.code in (gp.GP_ERROR_BAD_PARAMETERS, gp.GP_ERROR_NOT_SUPPORTED, gp.GP_ERROR):
                return None
            raise self._translate(error) from error

    def _text(self, name: str) -> str | None:
        widget = self._single(name)
        if widget is None:
            return None
        value = widget.get_value()
        return None if value is None else str(value)

    def _collect(self, widget: Any, out: list[Setting], seen: set[str]) -> None:
        for index in range(widget.count_children()):
            child = widget.get_child(index)
            if child.get_type() in self._containers:
                self._collect(child, out, seen)
                continue
            setting = self._to_setting(child)
            if setting is not None and setting.name not in seen:
                seen.add(setting.name)
                out.append(setting)

    def _to_setting(self, widget: Any) -> Setting | None:
        kind = self._types.get(widget.get_type())
        if kind is None:
            return None
        raw = widget.get_value()
        choices: list[str] | None = None
        low = high = step = None
        value: SettingValue
        if kind == "choice":
            choices = [widget.get_choice(i) for i in range(widget.count_choices())]
            value = "" if raw is None else str(raw)
        elif kind == "range":
            low, high, step = (float(n) for n in widget.get_range())
            value = float(raw)
        elif kind in ("toggle", "date"):
            value = int(raw)
        else:
            value = "" if raw is None else str(raw)
        return Setting(
            name=widget.get_name(),
            label=widget.get_label(),
            type=kind,
            value=value,
            readonly=bool(widget.get_readonly()),
            choices=choices,
            min=low,
            max=high,
            step=step,
        )
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_gphoto.py -q && pytest -q`
Expected: all pass, whole suite green.

- [ ] **Step 6: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add src/lensmind/camera/gphoto.py tests/fake_gphoto2.py tests/test_gphoto.py
git commit -m "$(printf 'Add libgphoto2 camera, tested against the real D3500 config tree\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 10: Web app

**Files:**
- Create: `web/style.css`, `web/js/i18n.js`, `web/js/api.js`, `web/js/ui.js`, `web/js/store.js`, `web/js/viewfinder.js`, `web/js/tiles.js`, `web/js/controls.js`, `web/js/gallery.js`, `web/js/app.js`
- Modify: `web/index.html` (replace the placeholder)
- Test: `tests/test_web_static.py`

**Interfaces:**
- Consumes: the HTTP API of Task 8 (JSON shapes listed there).
- Produces: the phone UI. Module boundaries: `api.js` (fetch wrapper, `ApiError`), `i18n.js` (`setLanguage`, `t`), `ui.js` (`el`, `toast`), `store.js` (settings cache: `getSettings`, `onSettings`, `findSetting`, `refreshSettings`, `writeSetting`), `viewfinder.js` (`start`, `stop`, `isRunning`, `showMessage`), `tiles.js` (`initTiles`), `controls.js` (`initControls`), `gallery.js` (`showGallery`, `setLastShot`), `app.js` (router and wiring).

- [ ] **Step 1: Write the failing test**

`tests/test_web_static.py`:
```python
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
    for element_id in ["vf-img", "vf-overlay", "tiles", "shutter", "groups", "grid", "sheet", "toast"]:
        assert f'id="{element_id}"' in html


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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_web_static.py -q`
Expected: FAIL (placeholder page has no `/js/app.js`, modules 404).

- [ ] **Step 3: Write `web/index.html`**

```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0e0f11">
  <title>lensmind</title>
  <link rel="stylesheet" href="/style.css">
  <script type="module" src="/js/app.js"></script>
</head>
<body>
  <header class="statusbar">
    <span class="dot" id="conn-dot"></span>
    <span id="cam-model"></span>
    <span id="cam-mode"></span>
    <span id="cam-battery"></span>
  </header>

  <main>
    <section class="screen" id="screen-main">
      <div class="viewfinder">
        <img id="vf-img" alt="">
        <div class="vf-overlay" id="vf-overlay"></div>
      </div>
      <div class="tiles" id="tiles"></div>
      <div class="assistant" id="assistant">
        <p id="last-result"></p>
      </div>
    </section>

    <section class="screen" id="screen-controls" hidden>
      <h1><a class="back" href="#/" data-i18n-label="back">‹</a><span data-i18n="controls_title"></span></h1>
      <div id="groups"></div>
    </section>

    <section class="screen" id="screen-gallery" hidden>
      <h1><a class="back" href="#/" data-i18n-label="back">‹</a><span data-i18n="gallery_title"></span></h1>
      <div class="grid" id="grid"></div>
    </section>
  </main>

  <nav class="bottombar">
    <div class="bar-left">
      <a class="thumb-btn" href="#/gallery" data-i18n-label="last_shot"><img id="last-thumb-img" alt=""></a>
    </div>
    <button class="shutter" id="shutter" type="button" data-i18n-label="shutter"></button>
    <div class="bar-right">
      <a class="icon-btn" href="#/controls" data-i18n-label="controls">⚙</a>
      <button class="icon-btn" id="lv-toggle" type="button" data-i18n-label="liveview">👁</button>
    </div>
  </nav>

  <div class="sheet" id="sheet" hidden>
    <div class="sheet-panel">
      <h2 id="sheet-title"></h2>
      <div class="sheet-list" id="sheet-list"></div>
    </div>
  </div>

  <div class="photo-view" id="photo-view" hidden></div>
  <div class="toast" id="toast" role="status" hidden></div>
</body>
</html>
```

- [ ] **Step 4: Write `web/style.css`**

```css
:root {
  color-scheme: dark;
  --bg: #0e0f11;
  --surface: #1a1c20;
  --surface-2: #24272c;
  --border: #333840;
  --text: #f2f3f5;
  --muted: #9aa0a8;
  --accent: #ffb020;
  --danger: #ff5a5a;
  --ok: #3ccf6e;
  --radius: 14px;
  --gutter: 16px;
  --bar-h: 88px;
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }

html, body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

body {
  min-height: 100dvh;
  overflow-x: hidden;
  padding-bottom: calc(var(--bar-h) + env(safe-area-inset-bottom));
}

.statusbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  gap: 12px;
  align-items: center;
  padding: calc(10px + env(safe-area-inset-top)) var(--gutter) 10px;
  background: var(--bg);
  color: var(--muted);
  font-size: 14px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--danger); flex: none; }
.dot.on { background: var(--ok); }
#cam-model { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
#cam-battery { margin-left: auto; flex: none; }

.screen { padding: 0 var(--gutter); }
.screen h1 { display: flex; align-items: center; gap: 4px; margin: 12px 0; font-size: 20px; }
.back { min-width: 44px; padding: 4px 8px 4px 0; color: var(--text); text-decoration: none; font-size: 28px; line-height: 1; }

.viewfinder { position: relative; aspect-ratio: 3 / 2; overflow: hidden; border-radius: var(--radius); background: #000; }
.viewfinder img { display: block; width: 100%; height: 100%; object-fit: contain; }
.vf-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  text-align: center;
  color: var(--muted);
  pointer-events: none;
}

.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
.tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-height: 64px;
  padding: 6px 4px;
  border: 0;
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font: inherit;
}
.tile-label { font-size: 12px; color: var(--muted); }
.tile-value { font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.tile.readonly .tile-value { color: var(--muted); }

.assistant { min-height: 64px; color: var(--muted); overflow-wrap: anywhere; }

.bottombar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  height: calc(var(--bar-h) + env(safe-area-inset-bottom));
  padding: 0 var(--gutter) env(safe-area-inset-bottom);
  border-top: 1px solid var(--surface-2);
  background: rgba(14, 15, 17, 0.92);
}
.bar-left { justify-self: start; }
.bar-right { justify-self: end; display: flex; gap: 8px; }
.thumb-btn { display: block; width: 52px; height: 52px; overflow: hidden; border-radius: 10px; background: var(--surface); }
.thumb-btn img { width: 100%; height: 100%; object-fit: cover; }
.shutter { width: 72px; height: 72px; border: 4px solid var(--text); border-radius: 50%; background: var(--accent); }
.shutter:active { transform: scale(0.94); }
.shutter:disabled { opacity: 0.5; }
.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border: 0;
  border-radius: 50%;
  background: var(--surface);
  color: var(--text);
  font-size: 22px;
  text-decoration: none;
}
.icon-btn.active { background: var(--accent); color: #000; }

details { margin-bottom: 10px; border-radius: var(--radius); background: var(--surface); }
summary { min-height: 48px; padding: 14px 16px; font-weight: 600; cursor: pointer; }
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 16px;
  border-top: 1px solid var(--surface-2);
}
.row-label { flex: 1 1 140px; min-width: 0; overflow-wrap: anywhere; }
.row-value { color: var(--muted); overflow-wrap: anywhere; }
.row select,
.row input[type="text"],
.row input[type="number"],
.row input[type="datetime-local"] {
  max-width: 100%;
  min-height: 44px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--text);
  font: inherit;
}
.row select { flex: 1 1 160px; min-width: 0; }
.range, .inline { display: flex; flex: 1 1 200px; gap: 8px; align-items: center; min-width: 0; }
.range input[type="range"] { flex: 1; min-width: 0; }
.range input[type="number"] { width: 88px; }
.inline input { flex: 1; min-width: 0; }
.switch { width: 52px; height: 32px; accent-color: var(--accent); }
.row button, .sheet-list button, .photo-view button {
  min-height: 44px;
  padding: 0 14px;
  border: 0;
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--text);
  font: inherit;
}

.grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
.cell { aspect-ratio: 1; overflow: hidden; padding: 0; border: 0; border-radius: 6px; background: var(--surface); color: var(--muted); font: inherit; }
.cell img { display: block; width: 100%; height: 100%; object-fit: cover; }
.empty { color: var(--muted); }

.sheet { position: fixed; inset: 0; z-index: 20; display: flex; align-items: flex-end; background: rgba(0, 0, 0, 0.5); }
.sheet-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-height: 70dvh;
  padding: 12px var(--gutter) calc(16px + env(safe-area-inset-bottom));
  border-radius: var(--radius) var(--radius) 0 0;
  background: var(--surface);
}
.sheet-panel h2 { margin: 4px 0 10px; color: var(--muted); font-size: 16px; }
.sheet-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(84px, 1fr)); gap: 8px; overflow-y: auto; }
.sheet-list button.current { background: var(--accent); color: #000; }

.photo-view {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: calc(12px + env(safe-area-inset-top)) var(--gutter) calc(12px + env(safe-area-inset-bottom));
  background: #000;
}
.photo-view img { flex: 1; width: 100%; min-height: 0; object-fit: contain; }
.photo-view .close { align-self: flex-end; }
.downloads { display: flex; flex-wrap: wrap; gap: 8px; }
.downloads a { padding: 12px 14px; border-radius: 10px; background: var(--surface-2); color: var(--text); text-decoration: none; overflow-wrap: anywhere; }

.toast {
  position: fixed;
  left: var(--gutter);
  right: var(--gutter);
  bottom: calc(var(--bar-h) + 12px + env(safe-area-inset-bottom));
  z-index: 40;
  padding: 12px 14px;
  border-left: 4px solid var(--danger);
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--text);
  pointer-events: none;
}
```

- [ ] **Step 5: Write `web/js/i18n.js`**

```js
// Every user-facing string of the web app. The language comes from /api/status.
const STRINGS = {
  it: {
    back: "Indietro",
    controls_title: "Controlli manuali",
    gallery_title: "Galleria",
    shutter: "Scatta",
    controls: "Controlli manuali",
    liveview: "Live view",
    last_shot: "Ultimo scatto",
    not_connected: "Fotocamera non collegata",
    liveview_off: "Live view spento: tocca 👁 per accenderlo",
    capturing: "Scatto in corso…",
    captured: "Salvato: {files}",
    current_value: "(attuale) {value}",
    unknown_state: "sconosciuto",
    on: "On",
    off: "Off",
    save: "Salva",
    now: "Adesso",
    readonly_hint: "{label} non si può cambiare in questa modalità",
    no_photos: "Nessuno scatto",
    download: "Scarica {name}",
    close: "Chiudi",
    network_error: "Server non raggiungibile",
    role_shutter: "Tempo",
    role_aperture: "Diaframma",
    role_iso: "ISO",
    role_exposure_comp: "Comp. esp.",
  },
  en: {
    back: "Back",
    controls_title: "Manual controls",
    gallery_title: "Gallery",
    shutter: "Shoot",
    controls: "Manual controls",
    liveview: "Live view",
    last_shot: "Last shot",
    not_connected: "Camera not connected",
    liveview_off: "Live view off: tap 👁 to turn it on",
    capturing: "Shooting…",
    captured: "Saved: {files}",
    current_value: "(current) {value}",
    unknown_state: "unknown",
    on: "On",
    off: "Off",
    save: "Save",
    now: "Now",
    readonly_hint: "{label} cannot be changed in this mode",
    no_photos: "No shots yet",
    download: "Download {name}",
    close: "Close",
    network_error: "Server unreachable",
    role_shutter: "Shutter",
    role_aperture: "Aperture",
    role_iso: "ISO",
    role_exposure_comp: "Exp. comp.",
  },
};

let language = "it";

export function setLanguage(code) {
  if (STRINGS[code]) language = code;
  document.documentElement.lang = language;
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nLabel));
  }
}

export function t(key, params = {}) {
  let text = STRINGS[language][key] ?? STRINGS.en[key] ?? key;
  for (const [name, value] of Object.entries(params)) text = text.replaceAll(`{${name}}`, String(value));
  return text;
}
```

- [ ] **Step 6: Write `web/js/api.js`**

```js
import { t } from "./i18n.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new ApiError(t("network_error"), 0);
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // keep the status text
    }
    throw new ApiError(detail, response.status);
  }
  return response;
}

export const api = {
  status: async () => (await request("GET", "/api/status")).json(),
  settings: async () => (await request("GET", "/api/settings")).json(),
  set: async (name, value) =>
    (await request("PUT", `/api/settings/${encodeURIComponent(name)}`, { value })).json(),
  capture: async () => (await request("POST", "/api/capture")).json(),
  preview: async () => (await request("GET", "/api/preview")).blob(),
  stopLiveview: () => request("POST", "/api/liveview/stop"),
  photos: async (limit = 60) => (await request("GET", `/api/photos?limit=${limit}`)).json(),
};
```

- [ ] **Step 7: Write `web/js/ui.js`**

```js
// DOM helpers. Text always goes through textContent or properties, never HTML.
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (key in node && !key.includes("-")) node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

let toastTimer = null;

export function toast(message) {
  const box = document.getElementById("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    box.hidden = true;
  }, 4000);
}
```

- [ ] **Step 8: Write `web/js/store.js`**

```js
import { api } from "./api.js";

let current = { groups: [], primary: {} };
const listeners = new Set();

export function getSettings() {
  return current;
}

export function onSettings(listener) {
  listeners.add(listener);
  listener(current);
}

export function findSetting(name) {
  for (const group of current.groups) for (const setting of group.settings) if (setting.name === name) return setting;
  return null;
}

function publish() {
  for (const listener of listeners) listener(current);
}

export async function refreshSettings() {
  current = await api.settings();
  publish();
}

export async function writeSetting(name, value) {
  const updated = await api.set(name, value);
  current = {
    ...current,
    groups: current.groups.map((group) => ({
      ...group,
      settings: group.settings.map((setting) => (setting.name === name ? updated : setting)),
    })),
  };
  publish();
  // Other settings can follow: in A mode the camera picks the shutter speed.
  refreshSettings().catch(() => {});
  return updated;
}
```

- [ ] **Step 9: Write `web/js/viewfinder.js`**

```js
import { api } from "./api.js";
import { t } from "./i18n.js";

let running = false;
let generation = 0;
let frameUrl = null;

export function isRunning() {
  return running;
}

export function showMessage(text) {
  const overlay = document.getElementById("vf-overlay");
  overlay.textContent = text;
  overlay.hidden = !text;
}

function updateButton() {
  document.getElementById("lv-toggle").classList.toggle("active", running);
}

export function start() {
  if (running) return;
  running = true;
  const run = ++generation;
  showMessage("");
  updateButton();
  loop(run);
}

export function stop({ beacon = false } = {}) {
  if (!running) return;
  running = false;
  generation++;
  updateButton();
  showMessage(t("liveview_off"));
  // While the page is being hidden a normal fetch may be dropped; a beacon is not.
  if (beacon && navigator.sendBeacon) navigator.sendBeacon("/api/liveview/stop");
  else api.stopLiveview().catch(() => {});
}

// One frame at a time: the next request leaves only after the previous frame is shown.
async function loop(run) {
  const img = document.getElementById("vf-img");
  while (running && run === generation) {
    try {
      const blob = await api.preview();
      if (run !== generation) return;
      const url = URL.createObjectURL(blob);
      await new Promise((resolve) => {
        img.onload = resolve;
        img.onerror = resolve;
        img.src = url;
      });
      if (frameUrl) URL.revokeObjectURL(frameUrl);
      frameUrl = url;
    } catch (error) {
      if (run !== generation) return;
      running = false;
      updateButton();
      showMessage(error.message);
      return;
    }
  }
}
```

- [ ] **Step 10: Write `web/js/tiles.js`**

```js
import { t } from "./i18n.js";
import { findSetting, onSettings, writeSetting } from "./store.js";
import { el, toast } from "./ui.js";

const ROLES = ["shutter", "aperture", "iso", "exposure_comp"];

export function initTiles() {
  document.getElementById("sheet").addEventListener("click", (event) => {
    if (event.target.id === "sheet") closeSheet();
  });
  onSettings(render);
}

function format(role, value) {
  if (role === "exposure_comp" && Number(value) > 0) return `+${value}`;
  return String(value);
}

function render({ primary }) {
  const tiles = [];
  for (const role of ROLES) {
    const setting = primary[role] ? findSetting(primary[role]) : null;
    if (!setting) continue;
    tiles.push(
      el(
        "button",
        { type: "button", className: setting.readonly ? "tile readonly" : "tile", onclick: () => pick(role, setting) },
        el("span", { className: "tile-label", text: t(`role_${role}`) }),
        el("span", { className: "tile-value", text: format(role, setting.value) + (setting.readonly ? " 🔒" : "") }),
      ),
    );
  }
  document.getElementById("tiles").replaceChildren(...tiles);
}

function pick(role, setting) {
  if (setting.readonly) {
    toast(t("readonly_hint", { label: t(`role_${role}`) }));
    return;
  }
  if (setting.type !== "choice") {
    location.hash = "#/controls";
    return;
  }
  const list = document.getElementById("sheet-list");
  document.getElementById("sheet-title").textContent = t(`role_${role}`);
  list.replaceChildren(
    ...setting.choices.map((choice) =>
      el("button", {
        type: "button",
        className: choice === setting.value ? "current" : "",
        text: format(role, choice),
        onclick: () => choose(setting.name, choice),
      }),
    ),
  );
  document.getElementById("sheet").hidden = false;
  list.querySelector(".current")?.scrollIntoView({ block: "center" });
}

async function choose(name, value) {
  closeSheet();
  try {
    await writeSetting(name, value);
  } catch (error) {
    toast(error.message);
  }
}

function closeSheet() {
  document.getElementById("sheet").hidden = true;
}
```

- [ ] **Step 11: Write `web/js/controls.js`**

```js
import { t } from "./i18n.js";
import { getSettings, onSettings, writeSetting } from "./store.js";
import { el, toast } from "./ui.js";

const TYPING = "input[type=text], input[type=number], input[type=datetime-local]";

export function initControls() {
  onSettings(render);
}

function render({ groups }) {
  const box = document.getElementById("groups");
  // Do not rebuild the list under the user's fingers while they type.
  if (box.contains(document.activeElement) && document.activeElement.matches(TYPING)) return;
  const open = new Set([...box.querySelectorAll("details[open]")].map((node) => node.dataset.group));
  box.replaceChildren(
    ...groups.map((group) => {
      const details = el("details", { open: open.has(group.name) }, el("summary", { text: group.label }), ...group.settings.map(row));
      details.dataset.group = group.name;
      return details;
    }),
  );
}

function row(setting) {
  return el(
    "div",
    { className: setting.readonly ? "row readonly" : "row" },
    el("span", { className: "row-label", text: setting.label }),
    setting.readonly ? el("span", { className: "row-value", text: `${display(setting)} 🔒` }) : editor(setting),
  );
}

function display(setting) {
  if (setting.type === "toggle") {
    if (setting.value === 1) return t("on");
    if (setting.value === 0) return t("off");
    return t("unknown_state");
  }
  if (setting.type === "date") return new Date(setting.value * 1000).toLocaleString();
  return String(setting.value);
}

function editor(setting) {
  switch (setting.type) {
    case "choice":
      return choiceEditor(setting);
    case "range":
      return rangeEditor(setting);
    case "toggle":
      return toggleEditor(setting);
    case "date":
      return dateEditor(setting);
    default:
      return textEditor(setting);
  }
}

function choiceEditor(setting) {
  const select = el("select", { "aria-label": setting.label, onchange: () => commit(setting, select.value, [select]) });
  if (!setting.choices.includes(setting.value)) {
    select.append(
      el("option", { value: String(setting.value), text: t("current_value", { value: setting.value }), disabled: true, selected: true }),
    );
  }
  for (const choice of setting.choices) {
    select.append(el("option", { value: choice, text: choice, selected: choice === setting.value }));
  }
  return select;
}

function rangeEditor(setting) {
  const attributes = { min: setting.min, max: setting.max, step: setting.step || "any", value: setting.value };
  const slider = el("input", { type: "range", "aria-label": setting.label, ...attributes });
  const number = el("input", { type: "number", inputMode: "decimal", "aria-label": setting.label, ...attributes });
  slider.addEventListener("input", () => {
    number.value = slider.value;
  });
  slider.addEventListener("change", () => commit(setting, Number(slider.value), [slider, number]));
  number.addEventListener("change", () => commit(setting, Number(number.value), [slider, number]));
  return el("div", { className: "range" }, slider, number);
}

function toggleEditor(setting) {
  const box = el("input", { type: "checkbox", className: "switch", checked: setting.value === 1, "aria-label": setting.label });
  box.indeterminate = setting.value !== 0 && setting.value !== 1;
  box.addEventListener("change", () => commit(setting, box.checked ? 1 : 0, [box]));
  return box;
}

function textEditor(setting) {
  const input = el("input", { type: "text", value: String(setting.value), "aria-label": setting.label });
  const save = el("button", { type: "button", text: t("save"), onclick: () => commit(setting, input.value, [input, save]) });
  return el("div", { className: "inline" }, input, save);
}

function dateEditor(setting) {
  const input = el("input", { type: "datetime-local", step: 1, value: toLocalInput(setting.value), "aria-label": setting.label });
  const now = el("button", {
    type: "button",
    text: t("now"),
    onclick: () => commit(setting, Math.floor(Date.now() / 1000), [input, now]),
  });
  input.addEventListener("change", () => {
    const millis = new Date(input.value).getTime();
    if (!Number.isNaN(millis)) commit(setting, Math.floor(millis / 1000), [input, now]);
  });
  return el("div", { className: "inline" }, input, now);
}

function toLocalInput(seconds) {
  const date = new Date(seconds * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

async function commit(setting, value, controls) {
  for (const control of controls) control.disabled = true;
  try {
    await writeSetting(setting.name, value);
  } catch (error) {
    toast(error.message);
    render(getSettings()); // put the controls back to the last known values
  } finally {
    for (const control of controls) control.disabled = false;
  }
}
```

- [ ] **Step 12: Write `web/js/gallery.js`**

```js
import { api } from "./api.js";
import { t } from "./i18n.js";
import { el, toast } from "./ui.js";

export async function showGallery() {
  const grid = document.getElementById("grid");
  let shots;
  try {
    shots = await api.photos(60);
  } catch (error) {
    toast(error.message);
    return;
  }
  if (shots.length === 0) {
    grid.replaceChildren(el("p", { className: "empty", text: t("no_photos") }));
    return;
  }
  grid.replaceChildren(
    ...shots.map((shot) =>
      el(
        "button",
        { type: "button", className: "cell", onclick: () => openShot(shot) },
        shot.thumb_url
          ? el("img", { src: shot.thumb_url, alt: shot.id, loading: "lazy" })
          : el("span", { text: shot.files.map((file) => file.name.split(".").pop()).join(" + ") }),
      ),
    ),
  );
}

function openShot(shot) {
  const view = document.getElementById("photo-view");
  const image = shot.files.find((file) => /\.jpe?g$/i.test(file.name));
  view.replaceChildren(
    el("button", {
      type: "button",
      className: "close",
      text: "✕",
      "aria-label": t("close"),
      onclick: () => {
        view.hidden = true;
      },
    }),
    image ? el("img", { src: image.url, alt: shot.id }) : null,
    el(
      "div",
      { className: "downloads" },
      ...shot.files.map((file) => el("a", { href: file.url, download: file.name, text: t("download", { name: file.name }) })),
    ),
  );
  view.hidden = false;
}

export function setLastShot(shot) {
  if (shot.thumb_url) document.getElementById("last-thumb-img").src = shot.thumb_url;
}
```

- [ ] **Step 13: Write `web/js/app.js`**

```js
import { api } from "./api.js";
import { initControls } from "./controls.js";
import { setLastShot, showGallery } from "./gallery.js";
import { setLanguage, t } from "./i18n.js";
import { findSetting, onSettings, refreshSettings } from "./store.js";
import { initTiles } from "./tiles.js";
import { toast } from "./ui.js";
import * as viewfinder from "./viewfinder.js";

const SCREENS = { "#/": "screen-main", "#/controls": "screen-controls", "#/gallery": "screen-gallery" };
const STATUS_POLL_MS = 15000;
let connected = false;
let capturing = false;

function route() {
  const hash = SCREENS[location.hash] ? location.hash : "#/";
  for (const [key, id] of Object.entries(SCREENS)) document.getElementById(id).hidden = key !== hash;
  if (hash === "#/gallery") showGallery();
  if (hash !== "#/") viewfinder.stop();
}

async function refreshStatus() {
  let status;
  try {
    status = await api.status();
  } catch (error) {
    status = { connected: false, detail: error.message };
  }
  if (status.language) setLanguage(status.language);
  const camera = status.camera;
  document.getElementById("conn-dot").classList.toggle("on", status.connected);
  document.getElementById("cam-model").textContent = status.connected ? camera.model : status.detail || t("not_connected");
  document.getElementById("cam-battery").textContent = status.connected && camera.battery ? `🔋 ${camera.battery}` : "";
  const wasConnected = connected;
  connected = status.connected;
  if (connected && !wasConnected) await refreshSettings().catch((error) => toast(error.message));
  if (!connected) viewfinder.showMessage(status.detail || t("not_connected"));
  else if (!viewfinder.isRunning()) viewfinder.showMessage(camera.liveview_blocked_reason || t("liveview_off"));
}

async function shoot() {
  if (capturing) return;
  capturing = true;
  const button = document.getElementById("shutter");
  const result = document.getElementById("last-result");
  button.disabled = true;
  result.textContent = t("capturing");
  try {
    const shot = await api.capture();
    setLastShot(shot);
    result.textContent = t("captured", { files: shot.files.map((file) => file.name).join(", ") });
  } catch (error) {
    result.textContent = "";
    toast(error.message);
  } finally {
    capturing = false;
    button.disabled = false;
  }
}

function showMode({ primary }) {
  const mode = primary.mode ? findSetting(primary.mode) : null;
  document.getElementById("cam-mode").textContent = mode ? String(mode.value) : "";
}

async function init() {
  setLanguage("it");
  initTiles();
  initControls();
  onSettings(showMode);
  document.getElementById("shutter").addEventListener("click", shoot);
  document.getElementById("lv-toggle").addEventListener("click", () => {
    if (viewfinder.isRunning()) viewfinder.stop();
    else viewfinder.start();
  });
  window.addEventListener("hashchange", route);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) viewfinder.stop({ beacon: true });
    else refreshStatus();
  });
  route();
  await refreshStatus();
  api.photos(1).then((shots) => shots[0] && setLastShot(shots[0])).catch(() => {});
  setInterval(refreshStatus, STATUS_POLL_MS);
}

init();
```

- [ ] **Step 14: Run the tests and a syntax check of every module**

```bash
pytest tests/test_web_static.py -q
mkdir -p .mjs.check && for f in web/js/*.js; do cp "$f" ".mjs.check/$(basename "$f" .js).mjs" && node --check ".mjs.check/$(basename "$f" .js).mjs" || exit 1; done; rm -rf .mjs.check; echo syntax-ok
```
Expected: tests pass; `syntax-ok`.

- [ ] **Step 15: Check it in a browser on the mock**

```bash
LENSMIND_MOCK=1 LENSMIND_PHOTOS_DIR=./photos lensmind
```
Open `http://localhost:8000` with a phone-sized window (e.g. 390×844 in the browser dev tools) and check:
- status bar shows D3500, `M`, battery; tiles show `1/125`, `f/5.6`, `100`, `0`;
- 👁 starts live view; frames refresh; 👁 again stops it;
- tap the shutter tile → bottom sheet → `1/30` → tile updates, live view brightens;
- shutter button → "Salvato: …JPG, …NEF"; thumbnail appears bottom-left; gallery shows the shot and both download links;
- ⚙ → every type writable: `iso` (choice), `burstnumber` (range), `fastfs` (toggle), `artist` (text, Salva), `datetime` (date, Adesso); a read-only value shows 🔒; `effectmode` shows "(attuale) Unknown value 000b";
- no horizontal scroll at 320 px width; the shutter is reachable with the thumb on every screen.

Restart with `LENSMIND_MOCK_DIAL=AUTO` and check that the viewfinder shows the camera's "P/A/S/M" message and the shutter/aperture tiles carry 🔒.

- [ ] **Step 16: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add web tests/test_web_static.py
git commit -m "$(printf 'Add phone web app: viewfinder, primary tiles, manual controls, gallery\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 11: Raspberry Pi deployment

**Files:**
- Create: `deploy/install.sh`, `deploy/lensmind.service`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: the `lensmind` console script (Task 8), the `pi` extra (Task 1).
- Produces: `sudo deploy/install.sh` run from the repository on the Pi installs and starts `lensmind.service` on port 80.

- [ ] **Step 1: Write the failing tests**

`tests/test_deploy.py`:
```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "deploy" / "install.sh"
SERVICE = ROOT / "deploy" / "lensmind.service"


def test_install_script_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(INSTALL)], check=True)


def test_install_script_covers_the_documented_steps() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    for needed in [
        "python3-venv python3-dev build-essential pkg-config libgphoto2-dev gphoto2",
        '"$REPO_DIR[pi]"',
        "usermod -aG plugdev",
        "/etc/lensmind.env",
        "LENSMIND_PORT=80",
        "systemctl enable --now lensmind.service",
    ]:
        assert needed in text


def test_service_unit() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    for line in [
        "User=@USER@",
        "WorkingDirectory=@REPO@",
        "EnvironmentFile=/etc/lensmind.env",
        "ExecStart=@REPO@/.venv/bin/lensmind",
        "AmbientCapabilities=CAP_NET_BIND_SERVICE",
        "Restart=on-failure",
    ]:
        assert line in text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_deploy.py -q`
Expected: FAIL (`deploy/install.sh` does not exist).

- [ ] **Step 3: Write `deploy/lensmind.service`**

```ini
[Unit]
Description=lensmind camera assistant
After=network-online.target
Wants=network-online.target

[Service]
User=@USER@
WorkingDirectory=@REPO@
EnvironmentFile=/etc/lensmind.env
ExecStart=@REPO@/.venv/bin/lensmind
AmbientCapabilities=CAP_NET_BIND_SERVICE
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Write `deploy/install.sh`**

```bash
#!/usr/bin/env bash
# Install lensmind on Raspberry Pi OS Lite. Run from the repository: sudo deploy/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-}"

if [[ $EUID -ne 0 || -z "$RUN_USER" || "$RUN_USER" == "root" ]]; then
  echo "Run it with sudo from the user that will run lensmind: sudo deploy/install.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y python3-venv python3-dev build-essential pkg-config libgphoto2-dev gphoto2

sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -e "$REPO_DIR[pi]"

# Access to the camera's USB device without root.
usermod -aG plugdev "$RUN_USER"

if [[ ! -f /etc/lensmind.env ]]; then
  cat > /etc/lensmind.env <<'EOF'
LENSMIND_PORT=80
LENSMIND_LANGUAGE=it
EOF
fi

sed -e "s|@USER@|$RUN_USER|g" -e "s|@REPO@|$REPO_DIR|g" \
  "$REPO_DIR/deploy/lensmind.service" > /etc/systemd/system/lensmind.service
systemctl daemon-reload
systemctl enable --now lensmind.service

echo "lensmind is running: http://$(hostname).local/"
```

```bash
chmod +x deploy/install.sh
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_deploy.py -q`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

```bash
ruff format . && ruff check --fix .
git add deploy tests/test_deploy.py
git commit -m "$(printf 'Add Raspberry Pi installer and systemd unit\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

---

### Task 12: Documentation sync and hardware checklist

**Files:**
- Modify: `CLAUDE.md` (layout, API table, status), `README.md` (configuration table, D3500 notes), `docs/cameras/nikon-d3500.md` (checklist results)

**Interfaces:**
- Consumes: everything above. No code.

- [ ] **Step 1: Update `CLAUDE.md`**

In the layout block under `camera/`, add after `mock.py`:
```
│   ├── mock_catalog.py # mock settings, loaded from data/nikon-d3500-M.txt
│   ├── mock_image.py  # synthetic scene for mock preview/capture
│   ├── dump.py        # parser for `gphoto2 --list-all-config` output
│   ├── primary.py     # primary roles → setting names
│   ├── messages.py    # user-facing strings of the camera layer
```
In the HTTP API table, add after `GET /api/photos`:
```
| GET | `/api/photos/{file}` | Download one stored file |
| GET | `/api/photos/{file}/thumb` | Its 400 px thumbnail |
```
Under "Status and build order", add one line after the phase list:
```
Current status: phase 1 implemented; hardware checklist in docs/cameras/nikon-d3500.md.
```

- [ ] **Step 2: Update `README.md`**

In the configuration table: change the `LENSMIND_PHOTOS_DIR` default to `~/lensmind-photos`, and add:
```
| `LENSMIND_MOCK_DIAL` | `M` | Dial position of the simulated camera (`M`, `A`, `AUTO`) |
| `LENSMIND_LIVEVIEW_IDLE_SECONDS` | `5` | Live view turns off after this many seconds without frames |
```
In "Notes on the Nikon D3500", replace the last bullet with:
```
- Live view over USB needs an SD card in the camera and the dial on P, S, A or M.
  Details and open questions: `docs/cameras/nikon-d3500.md`.
```

- [ ] **Step 3: Run the full suite and lint**

Run: `pytest -q && ruff check . && ruff format --check .`
Expected: all pass, no lint errors.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(printf 'Sync docs with the phase 1 implementation\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```

- [ ] **Step 5: Hardware checklist on the Pi (done together with the user)**

Charge the camera battery first (the last dump reported 20%). Then from the Mac:
```bash
rsync -av --exclude .venv --exclude .git --exclude photos ./ lensmind@lensmind.local:~/lensmind/
ssh lensmind@lensmind.local 'cd ~/lensmind && sudo deploy/install.sh'
```
Open `http://lensmind.local` on the phone with the D3500 connected, SD card in, dial on M, and fill in each item of the checklist in `docs/cameras/nikon-d3500.md`. For the ISO-in-AUTO item, read the EXIF of the downloaded JPEG (`exiftool` on the Mac or the phone's photo info). For the RAW timing, read the service log: `journalctl -u lensmind -f`.

- [ ] **Step 6: Record and commit the findings**

```bash
git add docs/cameras/nikon-d3500.md
git commit -m "$(printf 'Record D3500 hardware checklist results\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>')"
```
