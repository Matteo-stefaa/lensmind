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
        "effectmode",
        "Effect Mode",
        "choice",
        "Unknown value 000b",
        False,
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
