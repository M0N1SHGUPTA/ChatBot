"""
Wiring: builds every component once from Settings.

    container = build(Settings.from_env())

The API, CLI and evals build a container and use its pipelines and services.
Tests swap in fakes through the keyword arguments, e.g.
`build(settings, embedder=HashEmbedder(), retrieval=FakeRetrieval())`.
Building is cheap: the embedding model, the Chroma client and the LLM chain load on first use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.chat.service import ChatService
from app.chat.sessions import SessionStore
from app.config import Settings
from app.ingestion.loaders import DocumentLoader
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.splitter import TextSplitter
from app.leads.flow import LeadFlow
from app.leads.store import LeadStore
from app.retrieval import prompts
from app.retrieval.pipeline import RetrievalPipeline
from app.vectorstore.chroma import ChromaStore
from app.vectorstore.embeddings import HFEmbedder


@dataclass
class Container:
    settings: Settings
    embedder: object
    store: ChromaStore
    sessions: SessionStore
    lead_store: LeadStore
    retrieval: RetrievalPipeline
    ingestion: IngestionPipeline
    lead_flow: LeadFlow
    chat: ChatService


def build(
    settings: Optional[Settings] = None,
    *,
    embedder=None,
    store: Optional[ChromaStore] = None,
    sessions: Optional[SessionStore] = None,
    lead_store: Optional[LeadStore] = None,
    retrieval=None,
) -> Container:
    s = settings or Settings.from_env()

    embedder = embedder or HFEmbedder(s.embedding_model, offline=s.hf_offline)
    store = store or ChromaStore(s.chroma_path, s.collection_name, embedder)
    sessions = sessions or SessionStore(max_messages=s.history_max_messages)
    lead_store = lead_store or LeadStore(s.leads_db_path, s.leads_json_path)
    retrieval = retrieval or RetrievalPipeline(
        store=store,
        model=s.llm_model,
        temperature=s.llm_temperature,
        top_k=s.top_k,
        contextualize_prompt=prompts.CONTEXTUALIZE_PROMPT,
        answer_prompt=prompts.ANSWER_PROMPT,
    )
    ingestion = IngestionPipeline(
        DocumentLoader(), TextSplitter(s.chunk_size, s.chunk_overlap), store, s.knowledge_dir, retrieval
    )
    lead_flow = LeadFlow(lead_store, sessions, trigger_turn=s.lead_trigger_turn)
    chat = ChatService(retrieval, lead_flow, sessions)
    return Container(s, embedder, store, sessions, lead_store, retrieval, ingestion, lead_flow, chat)
