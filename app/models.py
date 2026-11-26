"""
Shared data types used by every pipeline. Plain dataclasses: no I/O, no third-party imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

Role = Literal["user", "assistant"]


@dataclass
class Document:
    """A loaded document or one chunk of it. metadata carries 'source', 'page', 'start_index'."""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> str:
        return str(self.metadata.get("source", "Unknown"))


@dataclass
class ScoredChunk:
    document: Document
    score: float  # distance: lower is closer


@dataclass
class Message:
    role: Role
    text: str


@dataclass
class LeadDraft:
    name: Optional[str] = None
    email: Optional[str] = None
    service: Optional[str] = None

    def is_complete(self) -> bool:
        return bool(self.name and self.email and self.service)


@dataclass
class Lead:
    session_id: str
    name: str
    email: str
    service: str
    notes: Optional[str] = None
    created_at: str = ""
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "session_id": self.session_id,
            "name": self.name,
            "email": self.email,
            "service": self.service,
            "notes": self.notes,
            "created_at": self.created_at,
        }
        if self.id is not None:
            d["id"] = self.id
        return d


@dataclass
class LeadReply:
    """What the lead flow says back when a message carried lead details."""

    answer: str
    is_complete: bool
    lead: Optional[Lead] = None


@dataclass
class Answer:
    """Output of the retrieval pipeline: the answer text and the chunks it was based on."""

    text: str
    context: List[Document] = field(default_factory=list)


@dataclass
class StreamEvent:
    """One item of a streamed answer: the retrieved chunks first, then tokens."""

    kind: Literal["context", "token"]
    token: str = ""
    context: List[Document] = field(default_factory=list)


@dataclass
class ChatResult:
    """Output of ChatService for one visitor message."""

    answer: str
    session_id: str
    turn_count: int
    trigger_lead_capture: bool  # lead capture active for this turn (computed before answering)
    context: List[Document] = field(default_factory=list)
    is_lead_intake: bool = False
    lead_complete: bool = False

    @property
    def source_names(self) -> List[str]:
        """Unique source file names, in first-seen order."""
        seen: List[str] = []
        for doc in self.context:
            name = doc.source.replace("\\", "/").rsplit("/", 1)[-1]
            if name not in seen:
                seen.append(name)
        return seen
