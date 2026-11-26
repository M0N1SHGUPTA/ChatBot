"""Admin endpoints: run the ingestion pipeline and list collected leads (X-Admin-API-Key required)."""
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.container import Container
from app.api.deps import get_container, require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin Document Management"], dependencies=[Depends(require_admin)])


@router.post("/upload")
async def upload_documents(files: List[UploadFile] = File(...), c: Container = Depends(get_container)):
    """Upload .pdf/.docx/.txt/.md files: saved to the knowledge folder and indexed."""
    results = [c.ingestion.upload(f.filename or "", f.file) for f in files]
    return {
        "status": "completed",
        "total_files": len(files),
        "total_chunks_added": sum(r.get("chunks_indexed", 0) for r in results),
        "files": results,
    }


@router.get("/documents")
async def list_documents(c: Container = Depends(get_container)):
    return c.ingestion.list_documents()


@router.delete("/documents/{filename}")
async def delete_document(filename: str, c: Container = Depends(get_container)):
    try:
        deleted = c.ingestion.delete(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File '{filename}' does not exist.")
    return {"status": "success", "message": f"Deleted '{filename}' and removed {deleted} chunks from vector store."}


@router.post("/reindex")
async def reindex(c: Container = Depends(get_container)):
    """Rebuild the vector index from every file in the knowledge folder."""
    n_docs, n_chunks = c.ingestion.reindex()
    if not n_docs:
        return {"status": "warning", "message": "No documents found to reindex."}
    return {"status": "success", "message": f"Successfully re-indexed {n_docs} documents into {n_chunks} chunks."}


@router.get("/leads")
async def list_leads(c: Container = Depends(get_container)):
    leads = [lead.to_dict() for lead in c.lead_flow.all_leads()]
    return {"total_leads": len(leads), "leads": leads}
