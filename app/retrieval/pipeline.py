"""
Retrieval pipeline: question + chat history -> answer grounded in the knowledge base.

    1. rewrite a follow-up into a standalone question (LLM, uses the history)
    2. search Chroma for the top-k chunks
    3. answer with those chunks as context (Groq LLM)

Stateless: ChatService owns the history and passes it in. Built on LangChain chains,
created lazily on first use and dropped by reload() after the index is rebuilt.
"""
from __future__ import annotations

from typing import AsyncIterator, List

from app.models import Answer, Document, Message, StreamEvent
from app.vectorstore.chroma import ChromaStore


class RetrievalPipeline:
    def __init__(
        self,
        store: ChromaStore,
        model: str,
        temperature: float,
        top_k: int,
        contextualize_prompt: str,
        answer_prompt: str,
    ) -> None:
        self.store = store
        self.model = model
        self.temperature = temperature
        self.top_k = top_k
        self.contextualize_prompt = contextualize_prompt
        self.answer_prompt = answer_prompt
        self._chain = None

    def reload(self) -> None:
        self._chain = None
        self.store.reload()

    def _get_chain(self):
        if self._chain is None:
            from langchain_classic.chains import create_history_aware_retriever, create_retrieval_chain
            from langchain_classic.chains.combine_documents import create_stuff_documents_chain
            from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
            from langchain_groq import ChatGroq

            llm = ChatGroq(model=self.model, temperature=self.temperature)
            retriever = self.store.langchain_retriever(self.top_k)

            def prompt(system: str):
                return ChatPromptTemplate.from_messages(
                    [("system", system), MessagesPlaceholder("chat_history"), ("human", "{input}")]
                )

            history_aware = create_history_aware_retriever(llm, retriever, prompt(self.contextualize_prompt))
            qa = create_stuff_documents_chain(llm, prompt(self.answer_prompt))
            self._chain = create_retrieval_chain(history_aware, qa)
        return self._chain

    @staticmethod
    def _inputs(question: str, history: List[Message]) -> dict:
        from langchain_core.messages import AIMessage, HumanMessage

        msgs = [HumanMessage(m.text) if m.role == "user" else AIMessage(m.text) for m in history]
        return {"input": question, "chat_history": msgs}

    @staticmethod
    def _docs(lc_docs) -> List[Document]:
        return [Document(text=d.page_content, metadata=dict(d.metadata)) for d in lc_docs or []]

    def answer(self, question: str, history: List[Message]) -> Answer:
        out = self._get_chain().invoke(self._inputs(question, history))
        return Answer(text=out.get("answer", ""), context=self._docs(out.get("context")))

    async def aanswer(self, question: str, history: List[Message]) -> Answer:
        out = await self._get_chain().ainvoke(self._inputs(question, history))
        return Answer(text=out.get("answer", ""), context=self._docs(out.get("context")))

    async def astream(self, question: str, history: List[Message]) -> AsyncIterator[StreamEvent]:
        async for chunk in self._get_chain().astream(self._inputs(question, history)):
            if "context" in chunk:
                yield StreamEvent(kind="context", context=self._docs(chunk["context"]))
            if "answer" in chunk:
                yield StreamEvent(kind="token", token=chunk["answer"])
