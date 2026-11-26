"""Health check and the demo page."""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.container import Container
from app.api.deps import get_container
from app.api.schemas import StatusResponse

router = APIRouter()


@router.get("/api/health", response_model=StatusResponse, tags=["System Health"])
async def health(c: Container = Depends(get_container)):
    return StatusResponse(
        status="healthy",
        model=f"{c.settings.llm_model} via Groq",
        total_chunks=c.ingestion.total_chunks(),
        documents=c.ingestion.document_names(),
    )


@router.get("/", response_class=HTMLResponse, tags=["Frontend Demo"])
async def demo_page(c: Container = Depends(get_container)):
    page = c.settings.static_dir / "index.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ChatBot API is Running! Visit <a href='/docs'>/docs</a> for Swagger</h1>")
