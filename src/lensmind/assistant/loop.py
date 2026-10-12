"""Conversations with the assistant: the model loop, its limits, the approval gate."""

import json
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from lensmind.assistant.prompts import msg, proposal_outcome, system_prompt
from lensmind.assistant.provider import Block, Provider, ProviderError, ToolCall
from lensmind.assistant.tools import (
    TOOLS,
    Proposal,
    ProposalRejected,
    ProposalState,
    build_proposal,
    camera_state,
    check_changes,
)
from lensmind.camera.base import Camera, CameraError

# Stop reasons of a finished reply; anything else (refusal, max_tokens) is an error.
COMPLETE = frozenset({"end_turn", "tool_use", "stop_sequence"})


class AssistantError(Exception):
    def __init__(self, message: str, status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class IncompleteReply(ProviderError):
    """The model stopped for a reason other than finishing its reply."""


@dataclass
class Turn:
    reply: str
    proposal: Proposal | None = None
    question: str | None = None
    finished: bool = False
    limit_reached: bool = False


@dataclass
class Conversation:
    id: str
    history: list[Block] = field(default_factory=list)
    # Tool results not sent yet: they open the next user message.
    pending_results: list[Block] = field(default_factory=list)
    # ask_user calls: the user's next text is their result.
    awaiting_answer: list[str] = field(default_factory=list)
    proposal: Proposal | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _Snapshot:
    length: int
    pending_results: list[Block]
    awaiting_answer: list[str]
    proposal: Proposal | None
    proposal_state: ProposalState | None
    proposal_reported: bool


@dataclass
class _Step:
    """What running the tool calls of one reply produced."""

    results: list[Block] = field(default_factory=list)
    proposal: Proposal | None = None
    question: str | None = None
    summary: str | None = None
    finished: bool = False

    @property
    def stops(self) -> bool:
        return self.proposal is not None or self.question is not None or self.finished


def tool_result(tool_use_id: str, content: str, error: bool = False) -> Block:
    block: Block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if error:
        block["is_error"] = True
    return block


class Assistant:
    def __init__(
        self,
        camera: Camera,
        provider: Provider,
        lang: str,
        max_turns: int,
        max_conversations: int = 20,
    ) -> None:
        self._camera = camera
        self._provider = provider
        self._lang = lang
        self._max_turns = max_turns
        self._max_conversations = max_conversations
        self._system = system_prompt(lang)
        self._conversations: OrderedDict[str, Conversation] = OrderedDict()
        self._registry_lock = threading.Lock()

    def start(self) -> Conversation:
        conversation = Conversation(id=uuid.uuid4().hex)
        with self._registry_lock:
            while len(self._conversations) >= self._max_conversations:
                self._conversations.popitem(last=False)
            self._conversations[conversation.id] = conversation
        return conversation

    def get(self, conversation_id: str) -> Conversation:
        with self._registry_lock:
            conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise AssistantError(msg(self._lang, "session_not_found"), 404)
        return conversation

    def send(self, conversation_id: str, text: str) -> Turn:
        conversation = self.get(conversation_id)
        if not conversation.lock.acquire(blocking=False):
            raise AssistantError(msg(self._lang, "busy"), 409)
        try:
            snapshot = _snapshot(conversation)
            try:
                return self._send(conversation, text)
            except ProviderError as error:
                _restore(conversation, snapshot)
                key = "incomplete" if isinstance(error, IncompleteReply) else "provider_error"
                raise AssistantError(msg(self._lang, key, error=error), 502) from error
        finally:
            conversation.lock.release()

    def apply(self, conversation_id: str, proposal_id: str) -> Proposal:
        conversation = self.get(conversation_id)
        if not conversation.lock.acquire(blocking=False):
            raise AssistantError(msg(self._lang, "busy"), 409)
        try:
            proposal = conversation.proposal
            if proposal is None or proposal.id != proposal_id:
                raise AssistantError(msg(self._lang, "proposal_not_found"), 404)
            if proposal.state != "pending":
                raise AssistantError(msg(self._lang, "proposal_not_pending"), 409)
            check_changes(self._camera, proposal.changes, self._lang)
            for change in proposal.changes:
                try:
                    self._camera.set(change.name, change.new)
                except CameraError as error:
                    proposal.failed = (change.name, error.message)
                    proposal.state = "partial" if proposal.applied else "failed"
                    return proposal
                proposal.applied.append(change)
            proposal.state = "applied"
            return proposal
        finally:
            conversation.lock.release()

    # Internals -----------------------------------------------------------------

    def _send(self, conversation: Conversation, text: str) -> Turn:
        blocks = [*conversation.pending_results]
        blocks += [tool_result(call_id, text) for call_id in conversation.awaiting_answer]
        proposal = conversation.proposal
        if proposal is not None and not proposal.reported:
            if proposal.state == "pending":
                proposal.state = "superseded"
            blocks.append(tool_result(proposal.tool_use_id, proposal_outcome(proposal)))
            proposal.reported = True
        conversation.pending_results, conversation.awaiting_answer = [], []
        blocks.append({"type": "text", "text": text})

        last_text = ""
        for _ in range(self._max_turns):
            conversation.history.append({"role": "user", "content": blocks})
            reply = self._provider.complete(self._system, conversation.history, TOOLS)
            if reply.stop_reason not in COMPLETE:
                raise IncompleteReply(reply.stop_reason)
            conversation.history.append({"role": "assistant", "content": reply.content})
            last_text = reply.text
            step = self._run_tools(conversation, reply.tool_calls)
            if step.stops or not reply.tool_calls:
                conversation.pending_results = step.results
                return Turn(
                    reply=_join(last_text, step.question, step.summary),
                    proposal=step.proposal,
                    question=step.question,
                    finished=step.finished,
                )
            blocks = step.results
        conversation.pending_results = blocks
        limit = msg(self._lang, "turn_limit", turns=self._max_turns)
        return Turn(reply=_join(last_text, limit), limit_reached=True)

    def _run_tools(self, conversation: Conversation, calls: list[ToolCall]) -> _Step:
        step = _Step()
        for call in calls:
            if call.name == "get_camera_state":
                step.results.append(self._camera_state(call))
            elif call.name == "propose_settings":
                self._propose(conversation, call, step)
            elif call.name == "ask_user":
                question = str(call.input.get("question", "")).strip()
                if not question:
                    step.results.append(tool_result(call.id, "question is empty", error=True))
                    continue
                conversation.awaiting_answer.append(call.id)
                step.question = _join(step.question, question)
            elif call.name == "finish":
                step.results.append(tool_result(call.id, "ok"))
                step.summary = str(call.input.get("summary", "")).strip() or None
                step.finished = True
            else:
                step.results.append(tool_result(call.id, f"Unknown tool: {call.name}", True))
        return step

    def _camera_state(self, call: ToolCall) -> Block:
        names = call.input.get("names")
        if names is not None and not (
            isinstance(names, list) and all(isinstance(name, str) for name in names)
        ):
            return tool_result(call.id, "names must be a list of setting names", error=True)
        try:
            state = camera_state(self._camera, names or None)
        except CameraError as error:
            return tool_result(call.id, error.message, error=True)
        return tool_result(call.id, json.dumps(state, ensure_ascii=False))

    def _propose(self, conversation: Conversation, call: ToolCall, step: _Step) -> None:
        if step.proposal is not None:
            text = "Only one proposal per reply: this one was ignored."
            step.results.append(tool_result(call.id, text, error=True))
            return
        try:
            proposal = build_proposal(self._camera, call.input, call.id)
        except ProposalRejected as rejected:
            lines = "\n".join(f"- {error}" for error in rejected.errors)
            text = f"Proposal rejected, nothing was shown to the user:\n{lines}"
            step.results.append(tool_result(call.id, text, error=True))
        except CameraError as error:
            step.results.append(tool_result(call.id, error.message, error=True))
        else:
            conversation.proposal = step.proposal = proposal


def _join(*parts: str | None) -> str:
    return "\n\n".join(part for part in parts if part)


def _snapshot(conversation: Conversation) -> _Snapshot:
    proposal = conversation.proposal
    return _Snapshot(
        length=len(conversation.history),
        pending_results=conversation.pending_results,
        awaiting_answer=conversation.awaiting_answer,
        proposal=proposal,
        proposal_state=proposal.state if proposal else None,
        proposal_reported=proposal.reported if proposal else False,
    )


def _restore(conversation: Conversation, snapshot: _Snapshot) -> None:
    del conversation.history[snapshot.length :]
    conversation.pending_results = snapshot.pending_results
    conversation.awaiting_answer = snapshot.awaiting_answer
    conversation.proposal = snapshot.proposal
    if snapshot.proposal is not None and snapshot.proposal_state is not None:
        snapshot.proposal.state = snapshot.proposal_state
        snapshot.proposal.reported = snapshot.proposal_reported
