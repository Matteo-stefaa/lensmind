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
- In AF-A/AF-S the body refuses to release when autofocus does not lock (dim room,
  low-contrast subject). libgphoto2 returns a bare `GP_ERROR` (-1, "Unspecified error");
  only the context error callback carries "Out of Focus" (PTP 0xa002). Setting
  `autofocus = Off` does not avoid it: libgphoto2 then shoots without focusing and the
  body still refuses (6/6 Out of Focus in AF-A).
- Manual focus over USB: `focusmode2 = MF (selection)` is accepted and the shot goes
  through; `MF (fixed)` is rejected (`GP_ERROR_BAD_PARAMETERS`).
- **libgphoto2's `capture()` can hang after an autofocus shot.** libgphoto2 2.5.34
  (`camera_nikon_capture`) sends InitiateCaptureRecInMedia (0x9207) and then polls
  DeviceReady (0x90c8) every 100 ms for up to 1000 s, without reading events and without
  checking the context cancel callback. In AF-A/AF-S/auto-area with enough light about
  every other shot is taken but DeviceReady answers Device Busy indefinitely; the call
  only ends when the process is killed. The next session then receives that shot's JPEG
  as its own first file and cannot download it ("You need to specify a folder starting
  with /store_xxxxxxxxx/"). The `gphoto2` CLI hangs the same way, also with the card as
  target. Not seen in MF, nor when autofocus fails (Out of Focus comes back in ~1.5 s).
  `trigger_capture()` has the same 1000 s wait.
- lensmind sends 0x9207 itself through the `opcode` widget
  (`0x9207,0xfffffffe,0x1`: autofocus, camera RAM; `0x0` targets the card) and reads the
  files from `wait_for_event`. Measured: 16/16 shots in AF-A, AF-S and MF where
  `capture()` hung on 2 of 4 in the same conditions; ~2.3 s per RAW+JPEG shot to RAM.
  The command itself returns Out of Focus (0xa002) when autofocus fails, but the widget
  reports every Nikon response as a bare `GP_ERROR`, with no context or log text reaching
  Python, so lensmind can only say the shot was refused and suggest focus as the usual cause.
- With the card as target the same command works, but the file events arrive about
  25 s after the shot (DeviceReady is OK after ~2 s). Cause not investigated.
- A python-gphoto2 `CameraWidget` is a sequence of its children: a leaf widget is falsy.
- In RAW+JPEG with Internal RAM the two files have different stems (`capt0001.jpg`,
  `capt0002.nef`); lensmind stores them under the first file's stem. `capture()` returns
  the JPEG; the NEF arrives as `GP_EVENT_FILE_ADDED` right after, then
  `GP_EVENT_CAPTURE_COMPLETE` about 0.7 s later.
- A file never downloaded stays in Internal RAM across sessions. It comes back as
  `GP_EVENT_FILE_ADDED` (folder `/`) before any capture, and libgphoto2 would return it as
  the next capture's first file. `file_delete` removes it without downloading (instant);
  lensmind drains events and deletes such leftovers before every capture.

## Hardware checklist (to run at the end of phase 1)

- [ ] Live view over USB works in M; frames per second on the phone: …
- [ ] `f-number = f/3.5` with the zoom at 55 mm: result …
- [ ] ISO set in AUTO is honoured in the EXIF of the shot: yes/no …
- [ ] RAW+JPEG: delay between the JPEG and the `GP_EVENT_FILE_ADDED` for the NEF: …
- [ ] Unplug and replug the cable while the app is open: status recovers yes/no …
- [ ] Live view stops on its own a few seconds after closing the page: yes/no …
- [ ] Shoot with live view never started: the capture succeeds (lensmind ignores the
      body's refusal to end a live view that is not running) …
- [ ] Shoot while live view runs, then watch the first frames after it: busy errors? …
- [ ] RAW+JPEG with Internal RAM: names of the two files (same stem or `capt0000`/`capt0001`?) …
- [ ] About 10 shots in a row with Internal RAM: any slowdown or "buffer full" error? …
- [ ] `datetime` set with "Adesso": the camera shows local time or UTC? …
