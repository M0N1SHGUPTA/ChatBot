"""
ChatService: the single path every visitor message takes (API, stream, CLI, evals).

    1. count the turn; note whether lead capture is active
    2. if the message carries lead details -> lead flow reply (no RAG)
    3. else -> retrieval pipeline with the session's history
    4. store the exchange in the session history
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

from app.chat.sessions import SessionStore
from app.leads.flow import LeadFlow
from app.models import ChatResult, Document, LeadReply, StreamEvent


@dataclass
class ChatStream:
    """Started stream: metadata is known up front, tokens arrive via `events()`."""

    session_id: str
    turn_count: int
    trigger_lead_capture: bool
    lead_reply: Optional[LeadReply]
    _service: "ChatService"
    _question: str
    context: List[Document] = field(default_factory=list)

    async def events(self) -> AsyncIterator[StreamEvent]:
        """RAG tokens. History is saved only once the answer has fully streamed."""
        svc = self._service
        history = svc.sessions.history(self.session_id)
        parts: List[str] = []
        async for ev in svc.retrieval.astream(self._question, history):
            if ev.kind == "context":
                self.context = ev.context
            elif ev.kind == "token":
                parts.append(ev.token)
            yield ev
        svc._remember(self.session_id, self._question, "".join(parts))

    @property
    def source_names(self) -> List[str]:
        return ChatResult("", self.session_id, 0, False, context=self.context).source_names


class ChatService:
    def __init__(self, retrieval, lead_flow: LeadFlow, sessions: SessionStore) -> None:
        self.retrieval = retrieval  # RetrievalPipeline (or a test fake)
        self.lead_flow = lead_flow
        self.sessions = sessions

    # --- shared steps ----------------------------------------------------------------------------
    def _begin(self, session_id: str, text: str):
        turn = self.sessions.increment_turns(session_id)
        trigger = self.lead_flow.is_active(session_id)
        reply = self.lead_flow.process(session_id, text)
        if reply:
            self._remember(session_id, text, reply.answer)
        return turn, trigger, reply

    def _remember(self, session_id: str, question: str, answer: str) -> None:
        self.sessions.append(session_id, "user", question)
        self.sessions.append(session_id, "assistant", answer)

    @staticmethod
    def _lead_result(session_id, turn, trigger, reply: LeadReply) -> ChatResult:
        return ChatResult(reply.answer, session_id, turn, trigger, is_lead_intake=True, lead_complete=reply.is_complete)

    # --- public API ------------------------------------------------------------------------------
    def handle_message(self, session_id: str, text: str) -> ChatResult:
        turn, trigger, reply = self._begin(session_id, text)
        if reply:
            return self._lead_result(session_id, turn, trigger, reply)
        ans = self.retrieval.answer(text, self.sessions.history(session_id))
        self._remember(session_id, text, ans.text)
        return ChatResult(ans.text, session_id, turn, trigger, context=ans.context)

    async def ahandle_message(self, session_id: str, text: str) -> ChatResult:
        turn, trigger, reply = self._begin(session_id, text)
        if reply:
            return self._lead_result(session_id, turn, trigger, reply)
        ans = await self.retrieval.aanswer(text, self.sessions.history(session_id))
        self._remember(session_id, text, ans.text)
        return ChatResult(ans.text, session_id, turn, trigger, context=ans.context)

    def start_stream(self, session_id: str, text: str) -> ChatStream:
        turn, trigger, reply = self._begin(session_id, text)
        return ChatStream(session_id, turn, trigger, reply, self, text)

    def clear(self, session_id: str) -> None:
        self.sessions.clear_history(session_id)
