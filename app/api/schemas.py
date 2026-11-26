"""HTTP request/response models (the API contract the UI relies on)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., examples=["What is RAG?"])
    session_id: str = Field(default="visitor_default", examples=["visitor_123"])


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    sources: List[str]
    message_count: int = Field(default=1, description="Number of turns in this session")
    trigger_lead_capture: bool = Field(default=False, description="True when visitor should be prompted for contact info")
    services: Optional[List[str]] = Field(default=None, description="The 8 available services to select from")


class LeadSubmissionRequest(BaseModel):
    session_id: str = Field(..., examples=["visitor_123"])
    name: str = Field(..., min_length=2, examples=["Alice Smith"])
    email: str = Field(..., examples=["alice@example.com"])
    service: str = Field(..., examples=["Market Landscaping"])
    notes: Optional[str] = Field(default=None, examples=["Looking for bilateral expansion opportunities"])


class LeadResponse(BaseModel):
    status: str
    message: str
    lead: Dict[str, Any]


class ServicesResponse(BaseModel):
    total_services: int
    services: List[str]


class ClearHistoryRequest(BaseModel):
    session_id: str = Field(..., examples=["visitor_123"])


class StatusResponse(BaseModel):
    status: str
    model: str
    total_chunks: int
    documents: List[str]
