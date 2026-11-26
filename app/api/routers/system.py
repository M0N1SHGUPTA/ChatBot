"""Health check and the demo page."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

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


@router.api_route("/widget.js", methods=["GET", "HEAD"], tags=["Frontend Demo"])
async def widget_script(c: Container = Depends(get_container)):
    """The embeddable chat widget: `<script src="https://<host>/widget.js" defer></script>`."""
    path = c.settings.static_dir / "widget.js"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="widget.js not found")
    return FileResponse(
        path,
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300", "Access-Control-Allow-Origin": "*"},
    )


@router.get("/widget-demo", response_class=HTMLResponse, tags=["Frontend Demo"])
async def widget_demo():
    """A blank host page with the widget embedded exactly as a third-party site would."""
    return HTMLResponse(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Widget demo</title></head>"
        "<body style='font-family:system-ui;background:#f8f7f4;color:#1a1a1a;padding:40px'>"
        "<h1>Widget demo</h1><p>The JIBB chat widget is embedded on this page with one script tag.</p>"
        "<button onclick=\"document.documentElement.classList.toggle('dark');"
        "document.body.style.background=document.documentElement.classList.contains('dark')?'#0f1629':'#f8f7f4'\">"
        "Toggle dark mode</button>"
        "<script src='/widget.js' defer></script></body></html>"
    )


@router.get("/", response_class=HTMLResponse, tags=["Frontend Demo"])
async def demo_page(c: Container = Depends(get_container)):
    page = c.settings.static_dir / "index.html"
    if page.exists():
        return HTMLResponse(page.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ChatBot API is Running! Visit <a href='/docs'>/docs</a> for Swagger</h1>")
