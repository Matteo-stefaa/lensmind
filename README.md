# lensmind

An AI assistant that sets up your camera for you.

Tell it what you want ("portrait, blurred background, sunset light"), and lensmind
chooses the settings, takes a test shot, looks at the result and refines until the
picture matches the intent. You drive it from your phone; the camera stays on its
tripod or in your hands.

> **Status: design stage.** Nothing below is implemented yet. This README describes
> the target; the [roadmap](#roadmap) shows the order in which it gets built.

## How it works

```
camera ──USB──> Raspberry Pi ──Wi-Fi──> phone (browser)
                │
                └──Internet──> AI model
```

- The **camera** is connected by USB cable to a Raspberry Pi.
- The **Raspberry Pi** runs lensmind: it talks to the camera through
  [libgphoto2](http://www.gphoto.org/), serves the web app and runs the assistant.
- The **phone** opens the web app in its browser. Nothing to install.
- The **AI model** receives your request, the current camera state and (from phase 3)
  a reduced copy of the test shot, and answers with the settings to change.

lensmind is not tied to one brand: it works with any camera libgphoto2 can control
remotely (Nikon, Canon, Sony, Fujifilm and others). Development and first tests
target the Nikon D3500.

## What the assistant can and cannot do

It can change whatever the camera exposes over USB: shutter speed, aperture, ISO,
exposure compensation, white balance, focus mode, image quality and so on. It can
take test shots and look at them.

It cannot move anything physical. When the mode dial, the zoom ring, your position
or an external flash need to change, it asks you to do it.

Every value the assistant proposes is checked against what the camera accepts at
that moment, and the number of test shots per request is capped: each one is a real
shutter actuation and a call to the AI model.

## Roadmap

| Phase | What you get |
|---|---|
| **1. Foundations** | Camera connection, simulated camera, HTTP API, web app with manual controls, live view and gallery. No AI yet. |
| **2. Assistant by words** | Describe the intent; the assistant proposes settings; you review the changes and approve. |
| **3. Assistant that looks** | The assistant receives a test shot (reduced image, histogram, shooting data) and proposes corrections. |
| **4. Full loop** | Intent → settings → test shot → evaluation → refinement, applied automatically within the configured limits. |

Each phase is usable on its own.

## Requirements

- A camera supported by libgphoto2 for remote capture
  ([list](http://www.gphoto.org/proj/libgphoto2/support.php)), with a USB **data** cable.
- A Raspberry Pi with Wi-Fi. A Pi Zero 2 W is enough in the field (it needs a USB OTG
  adapter); a Pi 4 or 5 is more comfortable for development and smoother in live view.
- Raspberry Pi OS **Lite**. The Desktop edition auto-mounts the camera and locks it.
- Python 3.11 or newer.
- From phase 2: an API key for the AI model and Internet access on the Pi.

## Try it without a camera

lensmind ships with a simulated camera, so you can run everything on a laptop.

```bash
git clone <repo-url> lensmind && cd lensmind
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
LENSMIND_MOCK=1 lensmind
```

Open `http://localhost:8000`, or `http://<laptop-ip>:8000` from your phone.

## Install on a Raspberry Pi

```bash
git clone <repo-url> ~/lensmind && cd ~/lensmind
sudo deploy/install.sh
```

The script installs libgphoto2, creates the Python environment and registers a
`lensmind` service that starts at boot. Then connect the camera, switch it on and
open `http://<pi-hostname>.local` from your phone.

To check the camera before starting lensmind:

```bash
gphoto2 --auto-detect     # the camera model must appear
gphoto2 --list-config     # the settings it exposes
```

### In the field

The assistant needs Internet, so the Pi cannot be the hotspot. Turn on the hotspot
on your phone and let the Pi join it:

```bash
sudo nmcli device wifi connect "<phone-hotspot-name>" password "<password>"
```

The Pi reconnects on its own the next time it sees that network.

## Configuration

Settings are read from environment variables (or from `/etc/lensmind.env` when
running as a service).

| Variable | Default | Meaning |
|---|---|---|
| `LENSMIND_MOCK` | `0` | `1` uses the simulated camera |
| `LENSMIND_HOST` | `0.0.0.0` | Address the server listens on |
| `LENSMIND_PORT` | `8000` | Port (the service uses `80`) |
| `LENSMIND_PHOTOS_DIR` | `./photos` | Where downloaded shots are stored |
| `ANTHROPIC_API_KEY` | – | API key for the AI model (phase 2 onward) |
| `LENSMIND_MODEL` | – | Model identifier used by the assistant |
| `LENSMIND_MAX_TEST_SHOTS` | `3` | Test shots allowed per request |
| `LENSMIND_LANGUAGE` | `it` | Language of the interface and of the assistant |

## Notes on the Nikon D3500

- The port is micro-USB. Charge-only cables do not work.
- The mode dial is physical. Shutter speed and aperture can be changed remotely only
  in the modes that allow it (M, S, A).
- With capture target "Internal RAM" the shot is downloaded to the Pi and not written
  to the SD card; with "Memory card" it is kept on the card too.
- Live view over USB and the exact set of writable settings still have to be
  confirmed on a real body; findings go in `docs/cameras/nikon-d3500.md`.

## Privacy and security

- From phase 3, reduced copies of your test shots are sent to the AI provider.
  Full-resolution files never leave the Pi.
- There is no authentication: anyone on the same network can control the camera.
  Use it on your home Wi-Fi or on your phone's hotspot; do not expose it to the Internet.
- The API key is stored on the Pi. Treat the SD card accordingly.

## Project layout

```
lensmind/
├── src/lensmind/
│   ├── camera/       # camera connection (libgphoto2 and simulated)
│   ├── assistant/    # AI: from a request to settings
│   ├── api/          # HTTP server
│   ├── storage.py    # downloaded shots
│   └── settings.py   # configuration
├── web/              # web app served to the phone
├── tests/
├── deploy/           # install script and systemd unit
└── docs/             # per-camera notes
```

Contributors and AI coding agents: see [CLAUDE.md](CLAUDE.md) for architecture rules,
commands and conventions.

## License

To be decided.
