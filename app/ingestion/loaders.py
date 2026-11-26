"""Step 1 of ingestion: read .pdf / .docx / .txt / .md files into Documents (LangChain loaders)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict, List

from app.models import Document

log = logging.getLogger(__name__)


def _loaders() -> Dict[str, Callable[[str], object]]:
    from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader

    return {
        ".pdf": PyPDFLoader,
        ".docx": Docx2txtLoader,
        ".doc": Docx2txtLoader,
        ".txt": lambda p: TextLoader(p, encoding="utf-8"),
        ".md": lambda p: TextLoader(p, encoding="utf-8"),
    }


class DocumentLoader:
    supported_extensions = {".pdf", ".docx", ".doc", ".txt", ".md"}

    def load_file(self, path: Path) -> List[Document]:
        ext = path.suffix.lower()
        if ext not in self.supported_extensions:
            raise ValueError(f"Unsupported file format '{ext}'")
        loaded = _loaders()[ext](str(path)).load()
        return [Document(text=d.page_content, metadata=dict(d.metadata)) for d in loaded]

    def load_dir(self, folder: Path) -> List[Document]:
        if not folder.exists():
            raise FileNotFoundError(f"Directory '{folder}' does not exist.")
        documents: List[Document] = []
        log.info("Scanning '%s' for documents...", folder)
        for path in sorted(folder.glob("**/*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.supported_extensions:
                log.info("  skipping unsupported format: %s", path.name)
                continue
            try:
                docs = self.load_file(path)
                documents.extend(docs)
                log.info("  loaded %s (%d page/section(s))", path.name, len(docs))
            except Exception as e:  # one bad file must not stop the others
                log.warning("  failed to load %s: %s", path.name, e)
        log.info("Total documents loaded: %d", len(documents))
        return documents
