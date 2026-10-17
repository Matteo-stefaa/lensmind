# Phase 3 — Assistant that looks: design

Date: 2026-10-17
Status: written after a first implementation (the code came before this spec); the
implementation is checked against it in the plan
`docs/superpowers/plans/2026-10-17-phase3-assistant-looks.md`.

Scope: a new `evaluate_shot` tool, `assistant/vision.py`, EXIF in mock captures, an
"evaluate the shot" shortcut in the web app. No automatic test shots and no automatic
application: both are phase 4. The approval gate of phase 2 is unchanged.

Done when:

1. `pytest` passes with the mock camera and the fake provider;
2. after a shot, the model receives a reduced JPEG (long edge ≤ 1024 px), histogram
   statistics and the shooting data, and can propose corrections through the normal
   proposal flow;
3. full-resolution files never leave the Pi;
4. manually, on the Pi with the D3500 and a real key: shoot, tap "Valuta lo scatto", get
   a sensible diagnosis and a proposal. Recorded in `docs/cameras/nikon-d3500.md`.

## 1. Decisions

| Topic | Decision |
|---|---|
| Who shoots | The user, with the shutter button. The model asks for a shot through its reply (or `ask_user`); `capture_test_shot` is phase 4 |
| Which shot | Always the newest shot in the photo store. No choice of an older one: the gallery is not part of the conversation |
| What the model gets | One `tool_result` with a JSON text block and an image block (base64 JPEG) |
| Image size | Long edge 1024 px, JPEG quality 80, EXIF orientation applied |
| Statistics | Computed on the reduced image (same histogram shape as full size, much cheaper on a Pi Zero) |
| Shooting data | From the JPEG's EXIF, not from the camera's current settings: the settings may have changed since the shot |
| Stale shots | The result says whether the shot was taken after the last applied proposal of this conversation (`true`/`false`, `null` if none applied) |
| RAW-only shots | Tool error telling the model to propose a quality that also records a JPEG. No RAW decoding (no dependency, too slow on the Pi) |
| History size | Only the newest 2 images stay in the conversation history; older ones become a text note. Their statistics stay |
| Web shortcut | After every successful capture the chat shows one "Evaluate the shot" card; tapping it sends a fixed request text. Typing a message removes the card |

## 2. `assistant/vision.py`

The only module of `assistant/` that imports Pillow.

```python
class PhotoSource(Protocol):            # PhotoStore satisfies it by structure
    def list_shots(self, limit: int = ...) -> Sequence[StoredShot]: ...
    def resolve(self, name: str) -> Path | None: ...

@dataclass(frozen=True)
class LatestShot:
    files: list[str]
    taken_at: float            # POSIX mtime of the newest file
    jpeg_name: str | None
    jpeg: bytes | None

@dataclass(frozen=True)
class ShotView:
    jpeg: bytes; width: int; height: int
    stats: dict[str, Any]; shooting: dict[str, Any]

def latest_shot(photos: PhotoSource) -> LatestShot | None
def view_shot(data: bytes) -> ShotView          # OSError if it cannot be decoded
def histogram_stats(image) -> dict[str, Any]
def shooting_data(exif) -> dict[str, Any]
```

`assistant/` does not import `storage.py`: the protocol keeps the dependency direction
`api → assistant → camera`, with `api/app.py` passing the store in.

Decoding uses `Image.draft("RGB", (1024, 1024))`, so a 24 MP JPEG is decoded at 1/2,
1/4 or 1/8 scale by libjpeg. `Image.DecompressionBombError` becomes `OSError`.

Statistics (percentages with one decimal):

| Key | Meaning |
|---|---|
| `mean_luminance`, `median_luminance` | 0–255, ITU-R 601 luma |
| `clipped_highlights_percent` | luma ≥ 250 |
| `clipped_shadows_percent` | luma ≤ 5 |
| `channel_clipped_percent` | per R/G/B, value 255 (catches a clipped red sunset) |
| `channel_mean` | per R/G/B: a hint of colour cast |
| `luminance_histogram_percent` | 8 bins of 32 levels |

Shooting data, when present: `exposure_time` ("1/125 s", "2 s"), `f_number` ("f/5.6"),
`iso`, `exposure_compensation_ev`, `focal_length_mm`, `focal_length_35mm`,
`exposure_program`, `metering`, `white_balance` (auto/manual), `flash_fired`.
Non-finite or malformed values are skipped.

## 3. The `evaluate_shot` tool

No input. Result for the model (English, like every tool text):

```json
{"file": "...DSC_0001.JPG", "files_of_the_shot": [...], "seconds_since_shot": 12,
 "taken_after_last_applied_proposal": true, "image_size": [1024, 683],
 "stats": {...}, "shooting_data": {...} | "not recorded in the file"}
```

followed by the image block. Errors (`is_error: true`): no shot yet, no photo source,
no JPEG in the newest shot, JPEG unreadable.

`Conversation.applied_at` is set by `Assistant.apply` when at least one change was
written (`applied` or `partial`). `Assistant` takes `photos` and an injectable `clock`.

The system prompt tells the model to call `evaluate_shot` when the user took a shot or
asks how it came out, to trust the statistics over its impression for exposure, to check
`taken_after_last_applied_proposal`, to say briefly what is wrong and then propose, and
to ask the user to press the shutter when it needs a new shot.

## 4. Photo store

A capture writes its files while the model may be reading the newest shot. Files are
written to a hidden temporary name and renamed into place, so a reader never sees a
half-written JPEG (hidden names are already ignored by `list_shots` and `resolve`).

## 5. Mock camera

JPEG captures carry EXIF written from the current settings: model, exposure time,
f-number, ISO, exposure compensation, focal length, exposure program (M → manual,
A → aperture priority, AUTO → program). The NEF placeholder stays without metadata.

## 6. Web app

- `offerEvaluation()` in `assistant.js`, called by `app.js` after a successful capture
  when the assistant is available. At most one offer card exists; a new capture
  replaces it, "New conversation" and a typed message remove it.
- Tapping while a reply is pending does nothing (the card stays).
- Strings `shot_ready`, `evaluate`, `evaluate_request` in `i18n.js` (it/en).

## 7. Tests

- `test_vision.py`: downscale, no upscale, orientation, clipping stats, split-image
  stats, EXIF from the mock, long exposures, missing EXIF, non-JPEG, latest shot with
  and without JPEG.
- `test_assistant_loop.py`: image + stats sent; overexposure visible in stats; stale vs
  fresh shot; no shot; no photo source; RAW only; only 2 images kept.
- `test_api_assistant.py`: a shot captured through the API is what the model sees.
- `test_storage.py`: no temporary file is left behind after `save`.

## 8. Risks and open points

- Which EXIF fields the D3500 really writes and how long `view_shot` takes on the Pi:
  checklist in `docs/cameras/nikon-d3500.md`.
- The model may still read exposure from the picture rather than the numbers; the
  prompt asks it not to. To be judged in the manual test.
