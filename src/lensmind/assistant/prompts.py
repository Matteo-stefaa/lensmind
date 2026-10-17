"""System prompt, user-facing strings of the assistant layer, and texts for the model."""

from lensmind.assistant.tools import Proposal

LANGUAGE_NAMES = {"it": "Italian", "en": "English"}

SYSTEM_PROMPT = """\
You are lensmind, an assistant that sets up a camera connected to this device by USB.
The user says what they want to photograph; you choose the camera settings for it.

How to work:
- Call get_camera_state before proposing anything. Use only setting names and values it
  reports: allowed values change with the mode dial and the lens. Ask for other settings
  by name when you need them.
- Propose changes with propose_settings, one entry per setting, each with a short reason
  the user can understand. The user approves or declines the proposal as a whole and
  nothing changes before that. Never say a change was applied until a tool result says so.
- Read-only settings cannot be changed in the current mode. When the goal needs something
  only the user can do (turning the mode dial, zooming, moving, framing, using the flash),
  call ask_user with one clear request.
- If a proposal is rejected, read the allowed values in the error and correct it.
- When the user has taken a test shot, or asks how a shot came out, call evaluate_shot.
  Judge exposure from its statistics (clipped highlights and shadows, mean luminance)
  more than from the image, and check that the shot was taken after the last applied
  proposal before blaming those settings. Say in one or two sentences what is wrong,
  then propose the corrections. If it already matches the request, say so and finish.
- You cannot take shots yourself: ask the user to press the shutter button when you
  need a new test shot.
- Call finish when the request is done, with a short summary.
- Keep replies short: the user reads them on a phone, next to the viewfinder.
- Always write to the user in {language}.
"""

MESSAGES: dict[str, dict[str, str]] = {
    "it": {
        "session_not_found": "Conversazione non trovata: ricomincia",
        "proposal_not_found": "Proposta non trovata",
        "proposal_not_pending": "Questa proposta non si può più applicare",
        "busy": "L'assistente sta ancora rispondendo al messaggio precedente",
        "turn_limit": (
            "Mi fermo qui: ho raggiunto il limite di {turns} passaggi per messaggio. "
            "Dimmi come vuoi proseguire."
        ),
        "provider_error": "L'assistente non è raggiungibile ({error}). Riprova.",
        "incomplete": "L'assistente non ha completato la risposta ({error}). Riprova.",
    },
    "en": {
        "session_not_found": "Conversation not found: start again",
        "proposal_not_found": "Proposal not found",
        "proposal_not_pending": "This proposal can no longer be applied",
        "busy": "The assistant is still answering the previous message",
        "turn_limit": (
            "Stopping here: I reached the limit of {turns} steps per message. "
            "Tell me how you want to continue."
        ),
        "provider_error": "The assistant cannot be reached ({error}). Try again.",
        "incomplete": "The assistant did not finish its reply ({error}). Try again.",
    },
}


def system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.format(language=LANGUAGE_NAMES.get(lang, "English"))


def msg(lang: str, key: str, **params: object) -> str:
    return MESSAGES.get(lang, MESSAGES["en"])[key].format(**params)


def proposal_outcome(proposal: Proposal) -> str:
    """Result of `propose_settings` for the model, sent with the user's next message."""
    applied = ", ".join(f"{change.name}={change.new}" for change in proposal.applied)
    if proposal.state == "applied":
        return f"The user approved the proposal. Applied: {applied}."
    if proposal.state in ("partial", "failed") and proposal.failed is not None:
        name, detail = proposal.failed
        done = f"Applied: {applied}." if applied else "Nothing was applied."
        return (
            f"The user approved the proposal. {done} {name} failed: {detail}. "
            "The changes after it were not attempted."
        )
    return "Not applied: the user wrote a new message instead of approving."
