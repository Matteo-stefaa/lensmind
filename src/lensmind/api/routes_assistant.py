"""Assistant endpoints. Sync: model and camera calls block, FastAPI runs them in its thread pool."""

from fastapi import APIRouter, HTTPException, Request

from lensmind.api.messages import msg
from lensmind.api.schemas import MessageIn, ProposalOut, SessionOut, TurnOut
from lensmind.assistant.loop import Assistant

router = APIRouter(prefix="/api/assistant")


def _assistant(request: Request) -> Assistant:
    assistant: Assistant | None = request.app.state.assistant
    if assistant is None:
        language = request.app.state.settings.language
        raise HTTPException(503, detail=msg(language, "assistant_not_configured"))
    return assistant


@router.post("/sessions", status_code=201)
def start_session(request: Request) -> SessionOut:
    return SessionOut(id=_assistant(request).start().id)


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: str, body: MessageIn, request: Request) -> TurnOut:
    return TurnOut.from_turn(_assistant(request).send(session_id, body.text))


@router.post("/sessions/{session_id}/proposals/{proposal_id}/apply")
def apply_proposal(session_id: str, proposal_id: str, request: Request) -> ProposalOut:
    return ProposalOut.from_model(_assistant(request).apply(session_id, proposal_id))
