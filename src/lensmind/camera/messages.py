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
        "capture_refused": (
            "La fotocamera ha rifiutato lo scatto. Di solito succede quando non riesce a "
            "mettere a fuoco: inquadra un soggetto più contrastato o illuminato, oppure usa "
            "la messa a fuoco manuale"
        ),
        "capture_timeout": (
            "La fotocamera non ha consegnato la foto entro {seconds} secondi: "
            "la connessione verrà riaperta"
        ),
        "out_of_focus": (
            "La fotocamera non è riuscita a mettere a fuoco e non ha scattato: inquadra un "
            "soggetto più contrastato o illuminato, oppure usa la messa a fuoco manuale"
        ),
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
        "capture_refused": (
            "The camera refused to shoot. This usually means it could not focus: aim at a "
            "brighter or more contrasted subject, or switch to manual focus"
        ),
        "capture_timeout": (
            "The camera did not deliver the photo within {seconds} seconds: "
            "the connection will be reopened"
        ),
        "out_of_focus": (
            "The camera could not focus and did not shoot: aim at a brighter or more "
            "contrasted subject, or switch to manual focus"
        ),
        "gphoto_missing": (
            "libgphoto2 is not installed: start with LENSMIND_MOCK=1 "
            "or install it with pip install '.[pi]'"
        ),
    },
}


def msg(lang: str, key: str, **params: object) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    return table[key].format(**params)
