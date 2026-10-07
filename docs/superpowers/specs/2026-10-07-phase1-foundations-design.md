# Phase 1 — Foundations: design

Date: 2026-10-07
Status: approved in conversation, pending written review

Scope: `camera/` (interface, mock, gphoto, session), `storage.py`, `settings.py`, `api/`,
`web/` with manual controls, live view and gallery, `deploy/`. No assistant code.

Done when:

1. `pytest` passes on the mock camera (no libgphoto2, no network);
2. every setting type (choice, range, toggle, text, date, read-only) can be read and
   written from the web app against the mock;
3. the hardware checklist in `docs/cameras/nikon-d3500.md` has been run on the Pi with
   the D3500 and its results recorded.

## 1. Evidence from the real camera

Config dumps were taken from a Nikon D3500 (firmware V1.00, 18-55 kit lens, SD card
inserted) on a Raspberry Pi 5 with the dial on M, A and AUTO. They are stored in
`docs/cameras/d3500/` (moved there from `docs/camera/` as the first implementation step)
and drive both the mock catalog and the gphoto tests.

Findings that shape this design:

| Setting | M | A | AUTO |
|---|---|---|---|
| `shutterspeed2`, `shutterspeed` | writable | read-only | read-only |
| `f-number` | writable | writable | read-only |
| `iso`, `exposurecompensation`, `whitebalance`, `focusmode2` | writable | writable | writable (effect unverified) |
| `expprogram` (dial), `focusmode` | read-only | read-only | read-only |
| Live view | allowed | allowed | prohibited ("Exposure Program Mode is not P/A/S/M") |

- The same 117 widgets exist in every mode; only read-only flags and some choice lists
  change.
- **Choices change at runtime.** In M/A `f-number` offers f/3.5–f/22 (lens limits at
  18 mm); in AUTO it offers a generic f/1–f/22. `flashmode` choices also differ per mode.
- A current value may be outside the choices (`effectmode = "Unknown value 000b"`,
  `thumbsize = ""`).
- Toggles may read `2` (unknown state), e.g. `bulb`, `movie`.
- Names can repeat (`/main/actions/bulb` appears twice).
- `/main/other/*` (58 widgets) are raw PTP properties duplicating readable ones.
  `/main/actions/*` includes `opcode`, a writable text field that sends raw PTP commands.
- Live view requires an SD card and the dial on P/A/S/M; `liveviewprohibit` gives a
  readable reason.
- `capturetarget = Internal RAM`; `imagequality = NEF+Fine` produces two files per shot.
- The D3500 exposes no writable text setting in the sections we keep.

## 2. Camera layer

### 2.1 Models — `camera/base.py`

Plain frozen dataclasses (no Pydantic: `camera/` knows nothing about HTTP).

```python
SettingValue = str | float | int
SettingType = Literal["choice", "range", "toggle", "text", "date"]

@dataclass(frozen=True)
class Setting:
    name: str
    label: str                 # as reported by the camera, not translated
    type: SettingType
    value: SettingValue        # choice/text: str, range: float, toggle/date: int
    readonly: bool
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None

@dataclass(frozen=True)
class SettingGroup:
    name: str                  # "capturesettings"
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
    def __init__(self, message: str, status: int) -> None: ...

class CameraDisconnected(CameraError):
    """I/O failure: the session must drop the connection and reconnect lazily."""
```

The `Camera` protocol is the one in `CLAUDE.md` (`status`, `settings`, `set`, `capture`,
`preview`, `end_liveview`, `close`).

Rules taken from the evidence:

- the current value is kept even when it is not among `choices`;
- a toggle value is an `int` and may be `2`;
- on duplicate names the first occurrence wins.

### 2.2 Validation — `camera/base.py`

One function, used by both implementations so their rules cannot diverge:

```python
def validate(setting: Setting | None, name: str, value: object, lang: str) -> SettingValue
```

- unknown name → `CameraError(..., 404)`;
- read-only → `409`;
- wrong type or outside `choices` / `[min, max]` / not on `step` → `422`; the message
  lists the allowed values (choices, or min/max/step);
- coercion: range accepts `int` or `float`; toggle accepts `bool`, `0` or `1`; date
  accepts `int` (epoch seconds); choice and text accept `str`.

It returns the coerced value ready to write.

### 2.3 Primary settings — `camera/primary.py`

The only hardcoded names in the project: role → candidate names, first match wins.

| Role | Candidates |
|---|---|
| `shutter` | `shutterspeed2`, `shutterspeed` |
| `aperture` | `f-number`, `aperture` |
| `iso` | `iso` |
| `exposure_comp` | `exposurecompensation` |
| `white_balance` | `whitebalance` |
| `focus` | `focusmode2`, `focusmode` |
| `quality` | `imagequality` |
| `mode` | `expprogram` |

`resolve_primary(groups) -> dict[str, str]` returns only roles that were found.

### 2.4 User-facing messages — `camera/messages.py`

`MESSAGES = {"it": {...}, "en": {...}}` plus `msg(lang, key, **params)`. The language is
passed to the camera constructor; `camera/` never reads `settings.py`.

### 2.5 libgphoto2 implementation — `camera/gphoto.py`

- The only module importing `gphoto2`, imported lazily inside methods/constructor.
- Walk `get_config()` recursively. Map RADIO/MENU → choice, RANGE → range,
  TOGGLE → toggle, TEXT → text, DATE → date; skip SECTION/WINDOW/BUTTON.
- **Excluded sections:** `EXCLUDED_SECTIONS = {"actions", "other"}`, matched on the
  top-level section name under `/main`. On the D3500 this leaves 50 settings.
- `set(name, value)`: `get_single_config(name)`, rebuild the `Setting` from that fresh
  widget (choices change at runtime), `validate`, then `set_value` (`str` for
  choice/text, `float` for range, `int` for toggle/date) and `set_single_config`. Return
  the setting re-read after writing. A name in an excluded section is rejected as unknown.
- `capture()`: turn live view off, `capture(GP_CAPTURE_IMAGE)`, then poll
  `wait_for_event` for about 1.5 s for `GP_EVENT_FILE_ADDED`. Download every file with
  `file_get(..., GP_FILE_TYPE_NORMAL)` and `bytes(memoryview(get_data_and_size()))`.
- `preview()`: `capture_preview()`. Before calling, read `liveviewprohibit` if present;
  when it reports a prohibition, raise `CameraError(reason, 409)`. `status().can_preview`
  comes from `abilities.operations & GP_OPERATION_CAPTURE_PREVIEW`.
- `end_liveview()`: set `viewfinder = 0` (internal use; `viewfinder` is in `actions`
  and therefore not exposed).
- Error mapping:

| gphoto2 error | Result |
|---|---|
| `GP_ERROR_BAD_PARAMETERS` | `CameraError` 422 |
| `GP_ERROR_NOT_SUPPORTED` | `CameraError` 409 |
| `GP_ERROR_CAMERA_BUSY` | `CameraError` 503 |
| generic `GP_ERROR` | `CameraError` 500 |
| `GP_ERROR_MODEL_NOT_FOUND` | `CameraDisconnected` 503 "camera not connected" |
| `GP_ERROR_IO_USB_CLAIM` | `CameraDisconnected` 503 "device held by another process" |
| any other I/O error | `CameraDisconnected` 503 |

### 2.6 Simulated camera — `camera/mock.py`, `camera/mock_catalog.py`

- `mock_catalog.py` holds the 50 settings of the D3500 M-mode dump: same names, labels,
  types, groups and choices.
- **One mock-only addition:** a writable text setting `artist` in `settings`, because the
  D3500 exposes none and the done criterion needs every type to be writable. It is
  commented as mock-only.
- **Dial:** `M`, `A`, `AUTO`. Initial position from `LENSMIND_MOCK_DIAL` (default `M`).
  `turn_dial(mode)` is a mock-only method, not part of `Camera`. The dial sets:
  - read-only flags per the table in §1;
  - `expprogram` value;
  - `f-number` choices: f/3.5–f/22 in M/A, f/1–f/22 in AUTO;
  - live view: blocked in AUTO with the camera's message.
- **Exposure model:** the scene has a fixed EV100 (12). Exposure error in stops
  (positive = overexposed) is `EV100 + log2(t · ISO/100 / N²)`. In M the user's values
  give the error directly. In A the mock picks the shutter choice whose error is closest
  to the exposure compensation; in AUTO it picks aperture and shutter the same way.
- **Image:** a deterministic synthetic scene drawn with Pillow (sky gradient, subject,
  very bright and very dark patches). Brightness is scaled by `2 ** error` and clipped,
  so highlights and shadows clip realistically.
  - `preview()`: 640×426 JPEG;
  - `capture()`: about 1500×1000 JPEG named `DSC_NNNN.JPG`; with `NEF+Fine` or
    `NEF (Raw)` also a placeholder `DSC_NNNN.NEF` (small, not an image).
- **Test hooks (mock-only):** `turn_dial(mode)`, `simulate_disconnect()` (next call
  raises `CameraDisconnected`).
- Validation goes through the shared `validate`.

### 2.7 Session — `camera/session.py`

`CameraSession(factory: Callable[[], Camera], idle_seconds: float, clock=time.monotonic)`
implements `Camera`.

- Every call holds one `threading.RLock`.
- Connects on first use by calling `factory()`.
- On `CameraDisconnected`: close and drop the camera, re-raise. The next call
  reconnects. Other `CameraError`s keep the session.
- `preview()` records the time of the last request and marks live view active.
- `capture()` calls `end_liveview()` first.
- A daemon watchdog thread wakes every second; if live view is active and idle for more
  than `idle_seconds`, it calls `end_liveview()` under the lock. The clock is injectable
  so tests do not sleep.
- `close()` stops the watchdog and closes the camera.

## 3. Configuration, storage and HTTP API

### 3.1 `settings.py`

A dataclass built from environment variables (no `pydantic-settings`).

| Variable | Default | Notes |
|---|---|---|
| `LENSMIND_MOCK` | `0` | `1` uses the simulated camera |
| `LENSMIND_MOCK_DIAL` | `M` | `M`, `A` or `AUTO` |
| `LENSMIND_HOST` | `0.0.0.0` | |
| `LENSMIND_PORT` | `8000` | the Pi service sets 80 |
| `LENSMIND_LANGUAGE` | `it` | `it` or `en` |
| `LENSMIND_PHOTOS_DIR` | `~/lensmind-photos` | |
| `LENSMIND_LIVEVIEW_IDLE_SECONDS` | `5` | |

Phase 2 variables are added in phase 2.

### 3.2 `storage.py`

- Save each `CapturedFile` as `YYYYMMDD-HHMMSS_<camera name>` in `LENSMIND_PHOTOS_DIR`,
  so camera numbering restarts do not overwrite files.
- Files sharing the prefix and stem form one **shot** (e.g. JPG + NEF).
- On save, a 400 px JPEG thumbnail goes to `.thumbs/`, using `Image.draft()` for fast
  JPEG decoding. Non-image files get no thumbnail; a shot's thumbnail is that of its
  first image file.
- `list_shots(limit)` returns shots newest first.
- `resolve(name)` returns a path only for a file name present in the photo directory
  listing; anything else (including `..`, slashes) is rejected.

### 3.3 `api/`

- `app.py`: lifespan builds `CameraSession` with the mock or gphoto factory from
  `settings`, stores it on `app.state`, closes it on shutdown. One exception handler maps
  `CameraError` → its status with `{"detail": message}`. `web/` is mounted on `/` after
  the API routes.
- Camera endpoints are sync functions (FastAPI runs them in its thread pool).
- `schemas.py`: Pydantic response/request models converted from the camera dataclasses.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/status` | Always 200: `{connected, detail?, language, camera?: CameraStatus}`. A connection failure becomes `connected: false` with the message. |
| GET | `/api/settings` | `{groups: [...], primary: {role: name}}` |
| PUT | `/api/settings/{name}` | Body `{"value": ...}`; returns the updated setting |
| POST | `/api/capture` | Shoots, saves, returns the shot (files, thumbnail URL) |
| GET | `/api/preview` | One JPEG frame, `Cache-Control: no-store`; 409 with the camera's reason when live view is prohibited |
| POST | `/api/liveview/stop` | 204 |
| GET | `/api/photos?limit=50` | Recent shots, newest first |
| GET | `/api/photos/{file}` | Download one file |
| GET | `/api/photos/{file}/thumb` | Its thumbnail |

The last two are additions to the table in `CLAUDE.md`, which is updated accordingly.

### 3.4 `__main__.py`

`lensmind` runs uvicorn on `LENSMIND_HOST:LENSMIND_PORT`.

## 4. Web app — `web/`

Plain HTML/CSS/JS, ES modules, no build, no CDN.

Files: `index.html`, `style.css`, `js/app.js` (hash router), `js/api.js`,
`js/viewfinder.js`, `js/controls.js`, `js/gallery.js`, `js/i18n.js` (all Italian and
English strings; language from `/api/status`).

### 4.1 Main screen — `#/`

```
┌──────────────────────────────┐
│ ● D3500   M   🔋 80%         │  status bar
├──────────────────────────────┤
│        VIEWFINDER 3:2        │  live view or placeholder;
│   overlay with reason        │  overlay pointer-events: none
├──────────────────────────────┤
│ 1/125 │ f/5.6 │ ISO 400 │ ±0 │  primary tiles → bottom-sheet picker
├──────────────────────────────┤
│ assistant area (phase 2)     │  in phase 1: last shot result
├──────────────────────────────┤
│ [thumb]     ( ◉ )   [⚙] [👁] │  shutter centred, thumb reach
└──────────────────────────────┘
```

- Tiles come from `primary`; read-only tiles are greyed with a lock.
- Bottom bar: last-shot thumbnail (→ gallery), shutter, controls (→ `#/controls`),
  live view on/off.

### 4.2 Manual controls — `#/controls`

All groups, collapsible.

| Type | Control |
|---|---|
| choice | native `<select>`; a current value outside choices appears as a disabled option "(current) …" |
| range | slider + number input |
| toggle | switch; value `2` shown as unknown |
| text | input + Save button |
| date | `datetime-local` + "Now" button |
| read-only | greyed value with lock |

While a write is pending the control is disabled; on error it reverts and a toast shows
the server's `detail`. After a successful write the app refetches `/api/settings`
in the background (changing aperture in A changes the shutter).

### 4.3 Gallery — `#/gallery`

Three-column thumbnail grid; tapping opens the large image with one download link per
file (JPG, NEF).

### 4.4 Live view

- Poll one frame at a time: request the next frame only after the previous one loaded
  (object URLs revoked after use).
- On 409, stop and show the reason in the overlay.
- On `visibilitychange` to hidden, stop and call `POST /api/liveview/stop`; the server
  watchdog covers the case where that call never arrives.

### 4.5 Rules

DOM built with `textContent` only; 16 px side gutters, no horizontal scroll, large
touch targets.

## 5. Project, tests and deploy

### 5.1 Project

- `git init`, `.gitignore` (`.venv`, `__pycache__`, `*.egg-info`, local photo folders).
- `pyproject.toml`: dependencies `fastapi`, `uvicorn`, `Pillow`; extra `pi` =
  `gphoto2`; extra `dev` = `pytest`, `ruff`, `httpx` (required by FastAPI's
  `TestClient`). `requires-python = ">=3.11"`.
- Development venv created with Python 3.11 (system `python3` on the Mac is 3.9).

### 5.2 Tests (all offline)

| File | Covers |
|---|---|
| `test_validate.py` | every type × 404/409/422, current value outside choices, coercion |
| `test_mock.py` | every type present; dial M/A/AUTO read-only flags and live view block; A computes shutter from aperture; mean luminance increases with exposure time; NEF+Fine yields 2 files |
| `test_session.py` | concurrent calls serialised; reconnect after `simulate_disconnect()`; capture ends live view; watchdog with a fake clock |
| `test_storage.py` | naming prefix, JPG+NEF grouping, thumbnails, malicious names rejected |
| `test_api.py` | every endpoint via `TestClient` on the mock; error status and `{"detail"}` body; `/api/status` when the camera fails to connect |
| `test_gphoto.py` | a fake `gphoto2` module injected into `sys.modules`, its widget tree parsed from the real dumps in `docs/cameras/d3500/`: tree walk, excluded sections, duplicates, type mapping, set flow, error mapping |

### 5.3 Deploy — `deploy/`

- `install.sh`: apt install `python3-venv python3-dev build-essential pkg-config
  libgphoto2-dev gphoto2`; create `.venv`; `pip install ".[pi]"`; add the user to
  `plugdev`; create `/etc/lensmind.env` if missing (with `LENSMIND_PORT=80`); install,
  enable and start `lensmind.service`.
- `lensmind.service`: runs as the installing user, `AmbientCapabilities=CAP_NET_BIND_SERVICE`,
  `EnvironmentFile=/etc/lensmind.env`, `Restart=on-failure`.

### 5.4 Hardware checklist (manual, on the Pi)

Recorded in `docs/cameras/nikon-d3500.md`:

- live view over USB works, and its frame rate;
- requesting f/3.5 at 55 mm (outside the lens's current range);
- whether ISO set in AUTO is honoured;
- RAW+JPEG: timing of the second file;
- unplugging and replugging the cable: the session reconnects.

## 6. Implementation order

Each step is tested before the next.

1. Project setup; move dumps to `docs/cameras/d3500/`; write `docs/cameras/nikon-d3500.md`.
2. `base.py`, `validate`, `messages.py`, `primary.py`.
3. Mock and its catalog.
4. Session.
5. Storage.
6. Settings and API.
7. gphoto with the fake module.
8. Web app.
9. Deploy.
10. Hardware checklist on the Pi.
