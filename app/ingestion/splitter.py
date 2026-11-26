"""Step 2 of ingestion: split Documents into overlapping chunks (RecursiveCharacterTextSplitter)."""
from __future__ import annotations

from typing import List

from app.models import Document


class TextSplitter:
    SEPARATORS = ["\n## ", "\n# ", "\n\n", "\n", " ", ""]

    def __init__(self, chunk_size: int = 1800, chunk_overlap: int = 300) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, documents: List[Document]) -> List[Document]:
        from langchain_core.documents import Document as LCDocument
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            add_start_index=True,  # character position in the original document
            separators=self.SEPARATORS,
        )
        lc_docs = [
            LCDocument(page_content=d.text.replace("\xa0", " "), metadata=dict(d.metadata))
            for d in documents
        ]
        return [
            Document(text=c.page_content, metadata=dict(c.metadata))
            for c in splitter.split_documents(lc_docs)
        ]
