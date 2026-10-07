"""User-facing messages of the API layer, per language."""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {"photo_not_found": "Foto non trovata: {name}"},
    "en": {"photo_not_found": "Photo not found: {name}"},
}


def msg(lang: str, key: str, **params: object) -> str:
    return MESSAGES.get(lang, MESSAGES["en"])[key].format(**params)
