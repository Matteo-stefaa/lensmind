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
        "gphoto_missing": (
            "libgphoto2 non è installato: avvia con LENSMIND_MOCK=1 "
            "oppure installa con pip install '.[pi]'"
        ),
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
        "gphoto_missing": (
            "libgphoto2 is not installed: start with LENSMIND_MOCK=1 "
            "or install it with pip install '.[pi]'"
        ),
    },
}


def msg(lang: str, key: str, **params: object) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    return table[key].format(**params)
