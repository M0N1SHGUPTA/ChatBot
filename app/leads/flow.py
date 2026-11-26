"""
Lead capture: pulls name / email / service out of visitor messages once capture is active
(from turn LEAD_TRIGGER_TURN on), and stores complete leads. Regex-based.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.chat.sessions import SessionStore
from app.leads import texts as lead_texts
from app.leads.catalog import SERVICES
from app.leads.store import LeadStore
from app.models import Lead, LeadReply

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Only explicit self-introductions count as a name; a bare short message is never a name.
NAME_PREFIX_REGEX = re.compile(
    r"\b(?:my name is|my name's|name\s*is|name\s*:|i am|i'm|i’m)\s+([A-Za-z][A-Za-z\s.'-]*)",
    re.IGNORECASE,
)
# Words that follow "I am" / "I'm" in sentences that are not introductions.
NOT_NAME_WORDS = {
    'a', 'an', 'the', 'not', 'interested', 'looking', 'from', 'with', 'in', 'at', 'here',
    'just', 'curious', 'trying', 'planning', 'working', 'based', 'also', 'still', 'very',
    'really', 'sorry', 'fine', 'good', 'ok', 'okay', 'sure', 'happy', 'glad', 'wondering',
    'asking', 'new', 'part', 'currently', 'going', 'thinking', 'considering', 'exploring',
}
_NAME_STOP = NOT_NAME_WORDS | {"and", "my", "email", "i"}


def extract_lead_fields(text: str) -> Dict[str, str]:
    """Lead fields explicitly present in this one message: any of name / email / service."""
    fields: Dict[str, str] = {}

    found = EMAIL_REGEX.findall(text)
    if found:
        email = found[0].rstrip(".-").lower()  # "bob@acme.com." -> "bob@acme.com"
        if "." in email.split("@", 1)[1]:
            fields["email"] = email

    lowered = text.lower()
    for svc in SERVICES:
        if svc.lower() in lowered:
            fields["service"] = svc
            break

    match = NAME_PREFIX_REGEX.search(text)
    if match:
        words = []
        for w in match.group(1).split():
            bare = w.strip(".'-")
            if not bare or bare.lower() in _NAME_STOP:
                break
            words.append(bare)
        if words and len(words) <= 4:
            fields["name"] = " ".join(words).title()

    return fields


class LeadFlow:
    def __init__(self, leads: LeadStore, sessions: SessionStore, trigger_turn: int = 2) -> None:
        self.leads = leads
        self.sessions = sessions
        self.trigger_turn = trigger_turn

    def is_active(self, session_id: str) -> bool:
        """Capture is active from turn `trigger_turn` on, until a lead is stored for the session."""
        if self.leads.exists_for_session(session_id):
            return False
        return self.sessions.turns(session_id) >= self.trigger_turn

    def process(self, session_id: str, text: str) -> Optional[LeadReply]:
        """A reply if this message carried lead details, else None (the message goes to RAG)."""
        clean = text.strip()
        if not clean or not self.is_active(session_id):
            return None
        fields = extract_lead_fields(clean)
        if not fields:
            return None

        draft = self.sessions.lead_draft(session_id)
        for key, value in fields.items():
            setattr(draft, key, value)

        if draft.is_complete():
            lead = self.submit(session_id, draft.name, draft.email, draft.service, "Captured via conversation")
            return LeadReply(lead_texts.captured(lead.name, lead.service, lead.email), is_complete=True, lead=lead)
        if draft.name and not draft.email:
            return LeadReply(lead_texts.ask_email_and_service(draft.name), is_complete=False)
        if draft.email and not draft.service:
            return LeadReply(lead_texts.ask_service(draft.name, draft.email), is_complete=False)
        if draft.service and not draft.email:
            return LeadReply(lead_texts.ask_email(draft.name, draft.service), is_complete=False)
        return None

    def submit(self, session_id: str, name: str, email: str, service: str, notes: Optional[str] = None) -> Lead:
        """Store a lead (from the conversation or the form). Normalises the fields."""
        return self.leads.save(Lead(
            session_id=session_id,
            name=name.strip(),
            email=email.strip().lower(),
            service=service.strip(),
            notes=notes.strip() if notes else None,
        ))

    def all_leads(self) -> List[Lead]:
        return self.leads.all()
