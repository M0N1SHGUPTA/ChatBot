"""Per-visitor conversation state kept in memory: history, turn count, partial lead details.

Lost on restart and not shared between worker processes.
"""
from __future__ import annotations

from typing import Dict, List

from app.models import LeadDraft, Message, Role


class SessionStore:
    def __init__(self, max_messages: int = 12) -> None:
        self.max_messages = max_messages
        self._history: Dict[str, List[Message]] = {}
        self._turns: Dict[str, int] = {}
        self._drafts: Dict[str, LeadDraft] = {}

    def history(self, session_id: str) -> List[Message]:
        return list(self._history.get(session_id, [])[-self.max_messages:])

    def append(self, session_id: str, role: Role, text: str) -> None:
        msgs = self._history.setdefault(session_id, [])
        msgs.append(Message(role=role, text=text))
        if len(msgs) > self.max_messages:
            del msgs[: len(msgs) - self.max_messages]

    def clear_history(self, session_id: str) -> None:
        self._history.pop(session_id, None)

    def increment_turns(self, session_id: str) -> int:
        self._turns[session_id] = self._turns.get(session_id, 0) + 1
        return self._turns[session_id]

    def turns(self, session_id: str) -> int:
        return self._turns.get(session_id, 0)

    def lead_draft(self, session_id: str) -> LeadDraft:
        return self._drafts.setdefault(session_id, LeadDraft())

    def reset(self) -> None:
        self._history.clear()
        self._turns.clear()
        self._drafts.clear()
