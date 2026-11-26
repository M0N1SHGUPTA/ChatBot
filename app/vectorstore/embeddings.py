"""Local sentence-transformers embeddings (CPU, model loaded on first use)."""
from __future__ import annotations

import os
from typing import List

from langchain_core.embeddings import Embeddings


class HFEmbedder(Embeddings):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", offline: bool = True) -> None:
        self.model_name = model_name
        self.offline = offline
        self._model = None

    def _load(self):
        if self._model is None:
            if self.offline:
                os.environ.setdefault("HF_HUB_OFFLINE", "1")  # no Hub checks for a cached model
            from langchain_huggingface import HuggingFaceEmbeddings

            self._model = HuggingFaceEmbeddings(
                model_name=self.model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._load().embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._load().embed_query(text)
