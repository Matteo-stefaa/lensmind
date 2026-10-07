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
# "Bulb" and "Time" have no fixed duration; the mock exposes them as this long.
UNTIMED_SECONDS = 30.0

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
    "f/1",
    "f/1.1",
    "f/1.2",
    "f/1.4",
    "f/1.6",
    "f/1.8",
    "f/2",
    "f/2.2",
    "f/2.5",
    "f/2.8",
    "f/3.2",
]
FILE_TYPES = {"NEF (Raw)": ("NEF",), "NEF+Fine": ("JPG", "NEF")}
NEF_PLACEHOLDER = b"lensmind mock NEF: not a real raw file\n"


def shutter_seconds(text: str) -> float | None:
    """Exposure time of a shutter choice ("1/125", "10/25", "30"), None for Bulb/Time."""
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / float(denominator)
        return float(text.removesuffix("s"))
    except ValueError:
        return None


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
        if mode == "AUTO":
            apertures = GENERIC_APERTURES + self._lens_apertures
        else:
            apertures = self._lens_apertures
        self._replace("f-number", choices=list(apertures))
        prohibit = LIVEVIEW_BLOCKED if mode == "AUTO" else LIVEVIEW_OK
        self._replace("liveviewprohibit", value=prohibit)
        if mode == "AUTO":
            self._liveview = False
        self._auto_expose()

    def simulate_disconnect(self) -> None:
        self._fail_next = True

    def exposure_error(self) -> float:
        """Stops above (positive) or below the correct exposure for the scene."""
        seconds = shutter_seconds(str(self._value("shutterspeed2"))) or UNTIMED_SECONDS
        return self._error(seconds, parse_aperture(str(self._value("f-number"))))

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
            if extension == "JPG":
                data = render(self.exposure_error(), CAPTURE_SIZE)
            else:
                data = NEF_PLACEHOLDER
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
        timed = [
            (index, seconds)
            for index, choice in enumerate(self._settings["shutterspeed2"].choices or [])
            if (seconds := shutter_seconds(choice)) is not None
        ]
        apertures = [str(self._value("f-number"))] if self._dial == "A" else self._lens_apertures
        _, _, index, aperture = min(
            (
                abs(self._error(seconds, parse_aperture(a)) - target),
                abs(math.log2(parse_aperture(a) / 5.6)),
                i,
                a,
            )
            for i, seconds in timed
            for a in apertures
        )
        self._set_shutter_index(index)
        self._replace("f-number", value=aperture)
