"""
Bridge between the eval runner and the chatbot under test.

The runner only talks to `get_adapter()`. It drives the same ChatService the API and CLI use,
built by the same app/container.py, so every eval run measures the real production path.

Contract:
    turn(session_id, text)      -> {"answer": str, "contexts": [str], "meta": dict}
    get_lead(session_id)        -> {"name", "email", "interest_category"} | None
    temporary_document(text)    -> context manager: index an extra doc for the duration
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from evals.taxonomy import category_for_service


class AppAdapter:
    name = "app"

    def __init__(self) -> None:
        from app.container import build

        self._build = build
        self.c = build()

    def turn(self, session_id: str, text: str) -> Dict[str, Any]:
        r = self.c.chat.handle_message(session_id, text)
        return {
            "answer": r.answer,
            "contexts": [d.text for d in r.context],
            "meta": {"is_lead_intake": r.is_lead_intake, "sources": [d.source for d in r.context]},
        }

    def get_lead(self, session_id: str) -> Optional[Dict[str, Any]]:
        rows = [lead for lead in self.c.lead_flow.all_leads() if lead.session_id == session_id]
        if not rows:
            return None
        row = rows[-1]  # all_leads() is newest first -> the first lead captured in this session
        return {
            "name": row.name,
            "email": row.email,
            "interest_category": category_for_service(row.service),
            "raw": row.to_dict(),
        }

    @contextmanager
    def temporary_document(self, text: str, source: str = "knowledge/__eval_injected__.md"):
        """Index `text` into a throwaway copy of the vector store; restore afterwards."""
        from app.models import Document

        original = self.c
        tmp = Path(tempfile.mkdtemp(prefix="eval_chroma_"))
        try:
            shutil.copytree(original.settings.chroma_path, tmp / "db")
            self.c = self._build(
                original.settings.with_overrides(chroma_path=tmp / "db"),
                embedder=original.embedder,
                sessions=original.sessions,
                lead_store=original.lead_store,
            )
            self.c.store.add(self.c.ingestion.splitter.chunk([Document(text, {"source": source})]))
            yield
        finally:
            self.c = original
            shutil.rmtree(tmp, ignore_errors=True)


def get_adapter():
    return AppAdapter()
