"""Public lead-generation endpoints (service list + lead form)."""
from fastapi import APIRouter, Depends, HTTPException

from app.container import Container
from app.leads.catalog import SERVICES
from app.api.deps import get_container
from app.api.schemas import LeadResponse, LeadSubmissionRequest, ServicesResponse

router = APIRouter(prefix="/api", tags=["Lead Generation"])


@router.get("/services", response_model=ServicesResponse)
async def services():
    return ServicesResponse(total_services=len(SERVICES), services=SERVICES)


@router.post("/leads", response_model=LeadResponse, status_code=201)
async def submit_lead(data: LeadSubmissionRequest, c: Container = Depends(get_container)):
    if "@" not in data.email or "." not in data.email:
        raise HTTPException(status_code=422, detail="Invalid email address format.")
    try:
        lead = c.lead_flow.submit(data.session_id, data.name, data.email, data.service, data.notes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record lead: {e}")
    return LeadResponse(status="success", message="Lead recorded successfully.", lead=lead.to_dict())
