"""User-facing messages of the API layer, per language."""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "photo_not_found": "Foto non trovata: {name}",
        "assistant_not_configured": (
            "Assistente non configurato: imposta ANTHROPIC_API_KEY e LENSMIND_MODEL"
        ),
    },
    "en": {
        "photo_not_found": "Photo not found: {name}",
        "assistant_not_configured": (
            "Assistant not configured: set ANTHROPIC_API_KEY and LENSMIND_MODEL"
        ),
    },
}


def msg(lang: str, key: str, **params: object) -> str:
    return MESSAGES.get(lang, MESSAGES["en"])[key].format(**params)
