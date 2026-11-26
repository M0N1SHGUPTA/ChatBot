"""
Persistent ChromaDB collection (via langchain-chroma), shared by both pipelines:
ingestion writes chunks into it, retrieval searches it.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from langchain_core.embeddings import Embeddings

from app.models import Document, ScoredChunk

log = logging.getLogger(__name__)


def generate_chunk_ids(chunks: List[Document]) -> List[str]:
    """Deterministic ids like 'knowledge/file.md:0:3' so re-indexing upserts instead of duplicating."""
    ids, counter = [], {}
    for doc in chunks:
        key = f"{doc.metadata.get('source', 'doc')}:{doc.metadata.get('page', 0)}"
        idx = counter.get(key, 0)
        counter[key] = idx + 1
        ids.append(f"{key}:{idx}")
    return ids


class _EmbedderBridge(Embeddings):
    """Wraps any object with embed_documents/embed_query (e.g. a test fake) as LangChain Embeddings."""

    def __init__(self, embedder) -> None:
        self._e = embedder

    def embed_documents(self, texts):
        return self._e.embed_documents(texts)

    def embed_query(self, text):
        return self._e.embed_query(text)


class ChromaStore:
    def __init__(self, path: Path, collection: str, embedder) -> None:
        self.path = Path(path)
        self.collection = collection
        self.embedder = embedder
        self._client = None
        self._store = None

    # --- internals ---------------------------------------------------------------------------
    def _embeddings(self) -> Embeddings:
        return self.embedder if isinstance(self.embedder, Embeddings) else _EmbedderBridge(self.embedder)

    def client(self):
        if self._client is None:
            import chromadb

            self._client = chromadb.PersistentClient(path=str(self.path))
        return self._client

    def langchain_store(self):
        """The underlying LangChain Chroma object (used by the retrieval pipeline)."""
        if self._store is None:
            from langchain_chroma import Chroma

            self._store = Chroma(
                client=self.client(),
                collection_name=self.collection,
                embedding_function=self._embeddings(),
            )
        return self._store

    def reload(self) -> None:
        self._store = None

    @staticmethod
    def _to_lc(chunks: List[Document]):
        from langchain_core.documents import Document as LCDocument

        return [LCDocument(page_content=c.text, metadata=dict(c.metadata)) for c in chunks]

    # --- public API ----------------------------------------------------------------------------
    def add(self, chunks: List[Document]) -> int:
        if not chunks:
            return 0
        self.langchain_store().add_documents(documents=self._to_lc(chunks), ids=generate_chunk_ids(chunks))
        return len(chunks)

    def replace_all(self, chunks: List[Document]) -> int:
        try:
            self.client().delete_collection(self.collection)
            log.info("Cleaned existing collection '%s'.", self.collection)
        except Exception:
            pass  # collection did not exist yet
        self.reload()
        log.info("Embedding and storing %d chunks in '%s'...", len(chunks), self.path)
        return self.add(chunks)

    def delete_source(self, source: str) -> int:
        try:
            ids = self.langchain_store().get(where={"source": source}).get("ids", [])
            if ids:
                self.langchain_store().delete(ids=ids)
            return len(ids)
        except Exception as e:
            log.warning("Error deleting chunks for %s: %s", source, e)
            return 0

    def stats(self) -> Dict:
        """Reads Chroma directly so it never loads the embedding model."""
        try:
            try:
                col = self.client().get_collection(self.collection)
            except Exception:
                return {"total_chunks": 0, "sources": {}}
            data = col.get(include=["metadatas"])
            sources: Dict[str, int] = {}
            for meta in data.get("metadatas") or []:
                if meta:
                    src = meta.get("source", "Unknown")
                    sources[src] = sources.get(src, 0) + 1
            return {"total_chunks": len(data.get("ids", [])), "sources": sources}
        except Exception as e:
            return {"total_chunks": 0, "sources": {}, "error": str(e)}

    def search(self, query: str, k: int) -> List[ScoredChunk]:
        results = self.langchain_store().similarity_search_with_score(query, k=k)
        return [
            ScoredChunk(Document(text=d.page_content, metadata=dict(d.metadata)), float(score))
            for d, score in results
        ]

    def langchain_retriever(self, k: int):
        return self.langchain_store().as_retriever(search_type="similarity", search_kwargs={"k": k})
