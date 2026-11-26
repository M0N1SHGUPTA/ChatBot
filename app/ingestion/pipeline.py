"""
Ingestion pipeline: knowledge files -> load -> split -> embed + store in Chroma.

    reindex()          rebuild the whole index from the knowledge folder
    upload(name, f)    save one file into the folder and index just that file
    delete(name)       remove a file and its chunks
    list_documents()   files on disk with their chunk counts

After the index changes, the retrieval pipeline is told to reload.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple

from app.ingestion.loaders import DocumentLoader
from app.ingestion.splitter import TextSplitter
from app.vectorstore.chroma import ChromaStore


class IngestionPipeline:
    def __init__(
        self,
        loader: DocumentLoader,
        splitter: TextSplitter,
        store: ChromaStore,
        knowledge_dir: Path,
        retrieval=None,
    ) -> None:
        self.loader = loader
        self.splitter = splitter
        self.store = store
        self.knowledge_dir = Path(knowledge_dir)
        self.retrieval = retrieval  # RetrievalPipeline (or a test fake), reloaded after reindex

    @property
    def allowed_extensions(self) -> set:
        return set(self.loader.supported_extensions)

    def _files(self) -> List[Path]:
        if not self.knowledge_dir.exists():
            return []
        return sorted(p for p in self.knowledge_dir.glob("*") if p.is_file() and not p.name.startswith("."))

    def document_names(self) -> List[str]:
        return [p.name for p in self._files()]

    def index_file(self, path: Path) -> int:
        docs = self.loader.load_file(path)
        if not docs:
            return 0
        return self.store.add(self.splitter.chunk(docs))

    def upload(self, filename: str, data: BinaryIO) -> Dict:
        """Save one uploaded file into the knowledge folder and index it. Never raises."""
        filename = Path(filename).name
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed_extensions:
            return {"filename": filename, "status": "error",
                    "error": f"Unsupported extension '{ext}'. Allowed: {sorted(self.allowed_extensions)}"}
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        target = self.knowledge_dir / filename
        with open(target, "wb") as buffer:
            shutil.copyfileobj(data, buffer)
        try:
            added = self.index_file(target)
            return {"filename": filename, "status": "success",
                    "size_bytes": target.stat().st_size, "chunks_indexed": added}
        except Exception as e:
            return {"filename": filename, "status": "error", "error": str(e)}

    def list_documents(self) -> Dict:
        stats = self.store.stats()
        in_db = stats.get("sources", {})
        docs = [{
            "filename": p.name,
            "file_type": p.suffix.lower(),
            "size_bytes": p.stat().st_size,
            "chunks_in_db": in_db.get(str(p), 0),
            "last_modified": p.stat().st_mtime,
        } for p in self._files()]
        return {"total_documents": len(docs), "total_chunks_in_db": stats.get("total_chunks", 0), "documents": docs}

    def delete(self, filename: str) -> int:
        """Remove the file and its chunks. Raises FileNotFoundError if it isn't there."""
        path = self.knowledge_dir / Path(filename).name
        if not path.is_file():
            raise FileNotFoundError(filename)
        path.unlink()
        return self.store.delete_source(str(path))

    def reindex(self) -> Tuple[int, int]:
        """Rebuild the whole index from the knowledge folder. Returns (documents, chunks)."""
        docs = self.loader.load_dir(self.knowledge_dir)
        if not docs:
            return 0, 0
        chunks = self.splitter.chunk(docs)
        self.store.replace_all(chunks)
        if self.retrieval is not None:
            self.retrieval.reload()
        return len(docs), len(chunks)

    def total_chunks(self) -> int:
        return self.store.stats().get("total_chunks", 0)
