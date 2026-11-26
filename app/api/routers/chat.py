"""Public chat endpoints: answer (JSON or SSE stream) and clear history."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.container import Container
from app.leads.catalog import SERVICES
from app.api.deps import get_container
from app.api.schemas import ChatRequest, ChatResponse, ClearHistoryRequest

router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, c: Container = Depends(get_container)):
    """Answer, cited source names, turn count and the lead-capture flag."""
    try:
        r = await c.chat.ahandle_message(request.session_id, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(
        answer=r.answer,
        session_id=r.session_id,
        sources=r.source_names,
        message_count=r.turn_count,
        trigger_lead_capture=r.trigger_lead_capture,
        services=SERVICES if r.trigger_lead_capture else None,
    )


@router.post("/stream")
async def chat_stream(request: ChatRequest, c: Container = Depends(get_container)):
    """Server-Sent Events: {"token"} events, then one final {"done": true, ...} event."""
    stream = c.chat.start_stream(request.session_id, request.message)

    if stream.lead_reply:
        reply = stream.lead_reply

        async def lead_events():
            for word in reply.answer.split(" "):
                yield _sse({"token": word + " "})
            yield _sse({
                "sources": [],
                "session_id": stream.session_id,
                "message_count": stream.turn_count,
                "trigger_lead_capture": not reply.is_complete,
                "services": SERVICES if not reply.is_complete else None,
                "done": True,
            })

        return StreamingResponse(lead_events(), media_type="text/event-stream")

    async def rag_events():
        try:
            async for ev in stream.events():
                if ev.kind == "token":
                    yield _sse({"token": ev.token})
            yield _sse({
                "sources": stream.source_names,
                "session_id": stream.session_id,
                "message_count": stream.turn_count,
                "trigger_lead_capture": stream.trigger_lead_capture,
                "services": SERVICES if stream.trigger_lead_capture else None,
                "done": True,
            })
        except Exception as e:
            yield _sse({"error": str(e), "done": True})

    return StreamingResponse(rag_events(), media_type="text/event-stream")


@router.post("/clear")
async def clear_history(request: ClearHistoryRequest, c: Container = Depends(get_container)):
    c.chat.clear(request.session_id)
    return {"status": "success", "message": f"Conversation memory cleared for session '{request.session_id}'"}
