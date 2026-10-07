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
