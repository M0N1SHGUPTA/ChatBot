"""Test doubles: same methods as the real components, without network, models or LLM calls."""
import hashlib
from typing import List

from app.models import Answer, Document, Message, StreamEvent


class HashEmbedder:
    """Deterministic bag-of-words embedder (stands in for HFEmbedder)."""

    def _vec(self, text):
        v = [0.0] * 64
        for w in text.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class FakeRetrieval:
    """Stands in for RetrievalPipeline: echoes the question and records what history it was given."""

    def __init__(self):
        self.calls: List[tuple] = []
        self.reloads = 0
        self.context = [Document("Tokyo office: Akasaka.", {"source": "knowledge/site.md"})]

    def _answer(self, question, history: List[Message]) -> Answer:
        self.calls.append((question, [(m.role, m.text) for m in history]))
        return Answer(text=f"ANSWER: {question}", context=list(self.context))

    def answer(self, question, history):
        return self._answer(question, history)

    async def aanswer(self, question, history):
        return self._answer(question, history)

    async def astream(self, question, history):
        ans = self._answer(question, history)
        yield StreamEvent(kind="context", context=ans.context)
        for word in ans.text.split(" "):
            yield StreamEvent(kind="token", token=word + " ")

    def reload(self):
        self.reloads += 1
