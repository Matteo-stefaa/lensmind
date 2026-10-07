# lensmind — guide for Claude Code

lensmind lets an AI assistant set up a tethered camera. A Raspberry Pi is connected
to the camera by USB, serves a web app to a phone, and runs an assistant that turns
an intent ("portrait, blurred background") into camera settings, takes test shots,
evaluates them and refines. See README.md for the user-facing description.

## Status and build order

The repository starts empty. Build in phases; finish and test one before starting
the next. Do not add assistant code before phase 1 is complete.

1. **Foundations** — `camera/` (interface, mock, gphoto), `api/`, `web/` with manual
   controls, live view, gallery, `deploy/`.
   Done when: the test suite passes on the mock camera and every setting type
   (choice, range, toggle, text, read-only) can be read and written from the web app.
2. **Assistant by words** — text intent → proposed changes → user approves → applied.
   Done when: a request produces a validated proposal with a reason per change, and
   nothing is applied without approval.
3. **Assistant that looks** — a test shot (downscaled image + histogram stats + shooting
   data) is evaluated and corrections are proposed.
4. **Full loop** — intent → apply → test shot → evaluate → refine, automatic, bounded
   by `LENSMIND_MAX_TEST_SHOTS`, with live progress in the web app.

Current status: phase 1 implemented; hardware checklist in docs/cameras/nikon-d3500.md.

## Commands

```bash
pip install -e ".[dev]"          # install with dev dependencies
LENSMIND_MOCK=1 lensmind         # run against the simulated camera, port 8000
pytest                           # tests (mock camera, fake AI provider)
ruff check . && ruff format .    # lint and format
```

There is no camera and no network in the development environment. Everything must
run with `LENSMIND_MOCK=1`, and tests must never call libgphoto2 on real hardware or
a real AI API.

## Layout

```
src/lensmind/
├── camera/
│   ├── base.py        # Camera protocol, Setting/SettingGroup/CameraStatus models, CameraError
│   ├── gphoto.py      # libgphoto2 implementation
│   ├── mock.py        # simulated camera
│   ├── mock_catalog.py # mock settings, loaded from data/nikon-d3500-M.txt
│   ├── mock_image.py  # synthetic scene for mock preview/capture
│   ├── dump.py        # parser for `gphoto2 --list-all-config` output
│   ├── primary.py     # primary roles → setting names
│   ├── messages.py    # user-facing strings of the camera layer
│   └── session.py     # single lock, reconnection, live-view idle shutdown
├── assistant/
│   ├── provider.py    # Provider protocol + Claude implementation + fake for tests
│   ├── tools.py       # tool definitions and their execution against Camera
│   ├── loop.py        # conversation / refinement loop, limits
│   ├── vision.py      # downscale, histogram stats, shooting data
│   └── prompts.py     # system prompt, per-language strings
├── api/
│   ├── app.py         # FastAPI app, lifespan, error handlers, static mount
│   ├── routes_camera.py
│   ├── routes_assistant.py
│   └── schemas.py
├── storage.py         # saving and listing downloaded shots
├── settings.py        # env-based configuration
└── __main__.py        # `lensmind` entry point (runs uvicorn)
web/                   # static web app, no build step
tests/
deploy/                # install.sh, lensmind.service
docs/cameras/          # per-model findings
```

## Architecture rules

- **Dependencies point one way:** `api → assistant → camera`. `camera/` knows nothing
  about HTTP or AI. `assistant/` knows nothing about HTTP.
- **Only `camera/gphoto.py` imports `gphoto2`.** Import it lazily so mock mode works
  without libgphoto2 installed.
- **Only `assistant/provider.py` imports the AI SDK.** The rest of `assistant/` talks
  to the `Provider` protocol, so the model can be swapped and faked.
- **The assistant never touches the camera directly.** It calls tools; `tools.py`
  executes them through the `Camera` interface.
- **Settings are discovered, not hardcoded.** The list comes from the camera at
  runtime. The only hardcoded names are a short table of "primary" settings with
  fallbacks (e.g. `shutterspeed2` → `shutterspeed`, `f-number` → `aperture`) used for
  the main tiles and for summarising state to the assistant.

## Camera layer

```python
class Camera(Protocol):
    def status(self) -> CameraStatus: ...          # model, battery, live-view support
    def settings(self) -> list[SettingGroup]: ...  # everything the camera exposes
    def set(self, name: str, value: SettingValue) -> Setting: ...
    def capture(self) -> list[CapturedFile]: ...   # name + bytes, one or more files
    def preview(self) -> bytes: ...                # one live-view JPEG frame
    def end_liveview(self) -> None: ...
    def close(self) -> None: ...
```

`Setting`: `name`, `label`, `type` (`choice | range | toggle | text | date`), `value`,
`readonly`, plus `choices` or `min/max/step`.

Rules:

- **One command at a time.** Every camera call goes through one re-entrant lock.
- **Validate before writing.** `set` rejects unknown names (404), read-only settings
  (409) and values outside `choices`/range (422) with `CameraError(message, status)`.
- **Reconnect lazily.** On an I/O error drop the session and reconnect on the next
  call. Keep the session on "soft" errors (`GP_ERROR_BAD_PARAMETERS`,
  `GP_ERROR_NOT_SUPPORTED`, `GP_ERROR_CAMERA_BUSY`, generic `GP_ERROR`).
- **Live view must not stay on.** While it is active the mirror is up and the battery
  drains. Turn it off (`viewfinder = 0`) before every capture and after a few seconds
  without preview requests (watchdog in `session.py`).
- **The mock is a first-class implementation.** It must cover every setting type,
  enforce the same validation, and render preview/capture images whose brightness
  reacts to shutter, aperture and ISO, so the assistant loop can be exercised.

### libgphoto2 facts already verified

Checked against python-gphoto2 2.6.4 (bundles libgphoto2 2.5.34, which lists
"Nikon DSC D3500"):

- Walk `camera.get_config()` recursively; widget types map as RADIO/MENU → choice,
  RANGE → range, TOGGLE → toggle, TEXT → text, DATE → date. Skip SECTION/WINDOW/BUTTON.
- Write with `get_single_config(name)` → `set_value()` → `set_single_config(name, w)`.
  `set_value` needs `str` for choice/text, `float` for range, `int` for toggle/date.
- Capture: `camera.capture(gp.GP_CAPTURE_IMAGE)` returns the first file path. In
  RAW+JPEG a second file arrives as `GP_EVENT_FILE_ADDED`; poll `wait_for_event` for
  about 1.5 s. Download with `file_get(folder, name, gp.GP_FILE_TYPE_NORMAL)` and
  `bytes(memoryview(camera_file.get_data_and_size()))`.
- Preview: `camera.capture_preview()`; support is advertised by
  `abilities.operations & gp.GP_OPERATION_CAPTURE_PREVIEW`.
- With no camera attached, `init()` raises `GP_ERROR_MODEL_NOT_FOUND`;
  `GP_ERROR_IO_USB_CLAIM` means another process (typically gvfs) holds the device.

Not yet verified on a real D3500: live view over USB, and which settings are writable
in each dial mode. Record findings in `docs/cameras/nikon-d3500.md`; do not encode
guesses as facts in code.

## Assistant layer

Tools exposed to the model:

| Tool | Purpose | From phase |
|---|---|---|
| `get_camera_state` | Primary settings, their allowed values, mode, lens, battery | 2 |
| `propose_settings` | List of `{name, value, reason}` for the user to approve | 2 |
| `ask_user` | Request a physical action (mode dial, zoom, position, flash) | 2 |
| `evaluate_shot` | Receive the latest test shot: image + histogram stats + shooting data | 3 |
| `apply_settings` | Apply changes directly | 4 |
| `capture_test_shot` | Take a test shot | 4 |
| `finish` | End the loop with a summary for the user | 2 |

Rules:

- **Validate every value** against the camera's current `choices`/range before
  applying. On mismatch return the allowed values to the model as a tool error; never
  apply a "closest" value silently.
- **Approval gate.** In phases 2–3 the model can only *propose*; the server applies
  after the user approves. Phase 4 adds automatic application, behind a per-session
  switch that defaults to off.
- **Hard limits in code, not in the prompt:** `LENSMIND_MAX_TEST_SHOTS` (default 3)
  and a cap on model turns per request. When a limit is hit, stop and report.
- **Send small images.** Downscale to about 1024 px on the long edge, JPEG. Add
  computed stats (mean luminance, clipped highlights/shadows %). Full-resolution
  files never leave the Pi.
- **Physical actions go to the user** through `ask_user`; the loop waits for the reply.
- **Model and key come from configuration** (`LENSMIND_MODEL`, `ANTHROPIC_API_KEY`).
  Do not hardcode a model identifier. With no key configured, the assistant endpoints
  return a clear error and the manual controls keep working.
- **Tests use a scripted fake provider.** Cover: invalid value rejected, approval
  required, limits enforced, physical action requested, loop converges on the mock.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Connection state, model, battery, capabilities |
| GET | `/api/settings` | All settings, grouped |
| PUT | `/api/settings/{name}` | Change one: `{"value": ...}` |
| POST | `/api/capture` | Shoot and download to the Pi |
| GET | `/api/preview` | One live-view frame (JPEG) |
| POST | `/api/liveview/stop` | Mirror down |
| GET | `/api/photos` | Recent shots |
| GET | `/api/photos/{file}` | Download one stored file |
| GET | `/api/photos/{file}/thumb` | Its 400 px thumbnail |
| POST | `/api/assistant/sessions` | Start a conversation |
| POST | `/api/assistant/sessions/{id}/messages` | Send text; returns reply and any proposal |
| POST | `/api/assistant/sessions/{id}/proposals/{pid}/apply` | Apply an approved proposal |
| GET | `/api/assistant/sessions/{id}/events` | Progress stream (SSE), phase 4 |

`CameraError` maps to its HTTP status with body `{"detail": "<message>"}`. Camera
endpoints are sync functions (they block on USB) so FastAPI runs them in its thread
pool. Live view is polled frame by frame by the client rather than streamed as MJPEG:
it gives natural back-pressure and lets the watchdog detect an idle client.

## Web app

- Plain HTML/CSS/JS in `web/`, no build step, no CDN (the Pi may be offline for
  static assets). Reconsider a framework only if it grows beyond two or three screens.
- Phone first: 16 px side gutters, no horizontal scroll, large touch targets, the
  shutter button always reachable with the thumb.
- Main screen: assistant conversation and viewfinder. Manual controls are a secondary
  screen. A proposal is shown as a list of changes (old → new, with the reason) and
  an approve button.
- Build DOM with `textContent`; never inject camera- or model-provided strings as HTML.
- Overlays that sit above controls need `pointer-events: none`.
- Stop live view when the page is hidden.

## Conventions

- Python 3.11+, type hints everywhere, `ruff` for lint and format.
- Code, comments, commit messages and docs in English. User-facing strings (web app,
  error messages, assistant replies) in the language set by `LENSMIND_LANGUAGE`,
  Italian by default; keep them in one place per layer, not scattered in logic.
- Dependencies stay minimal: `fastapi`, `uvicorn`, `gphoto2`, `Pillow`, the AI SDK.
  Ask before adding others; everything has to install on a Pi Zero 2 W.
- Configuration only through `settings.py` (env vars prefixed `LENSMIND_`).
- No authentication is planned for now; do not expose anything beyond the local network.

## Deployment facts

- Target: Raspberry Pi OS Lite. `deploy/install.sh` installs
  `python3-venv python3-dev build-essential pkg-config libgphoto2-dev gphoto2`, creates
  `.venv`, adds the user to `plugdev`, installs `lensmind.service`.
- The service runs as a normal user on port 80 via
  `AmbientCapabilities=CAP_NET_BIND_SERVICE`, and reads `/etc/lensmind.env`.
- In the field the phone is the hotspot and the Pi joins it, because the assistant
  needs Internet.
