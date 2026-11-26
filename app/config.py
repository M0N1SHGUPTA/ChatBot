"""
Settings: the only place environment variables are read.

Nothing happens at import time. Call `Settings.from_env()` (app/container.py does this)
and pass the object down; no other module reads os.environ or calls load_dotenv.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Knowledge base: folder holding ONLY documents the bot answers from (everything in it is indexed)
    knowledge_dir: Path = Path("knowledge")
    static_dir: Path = Path("static")

    # Vector store + embeddings
    chroma_path: Path = Path("chroma_db")
    collection_name: str = "chatbot_docs"
    embedding_model: str = "all-MiniLM-L6-v2"
    hf_offline: bool = True

    # Chunking
    chunk_size: int = 1800
    chunk_overlap: int = 300

    # Answering
    llm_model: str = "openai/gpt-oss-20b"
    llm_temperature: float = 0.2
    top_k: int = 5
    history_max_messages: int = 12  # last 6 turns

    # Leads
    lead_trigger_turn: int = 2  # lead capture becomes active from this user turn on (1-based)
    leads_db_path: Path = Path("leads.db")
    leads_json_path: Path = Path("leads.json")

    # Admin
    admin_api_key: str = "admin_secret_key_123"  # change via ADMIN_API_KEY in .env

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> "Settings":
        if load_dotenv_file:
            from dotenv import load_dotenv

            load_dotenv()  # also exposes GROQ_API_KEY / LANGCHAIN_* to the client libraries
        d = cls()
        env = os.getenv
        return cls(
            knowledge_dir=Path(env("KNOWLEDGE_DIR", str(d.knowledge_dir))),
            static_dir=Path(env("STATIC_DIR", str(d.static_dir))),
            chroma_path=Path(env("CHROMA_PATH", str(d.chroma_path))),
            collection_name=env("CHROMA_COLLECTION", d.collection_name),
            embedding_model=env("EMBEDDING_MODEL", d.embedding_model),
            hf_offline=_bool(env("HF_HUB_OFFLINE", "1" if d.hf_offline else "0")),
            chunk_size=int(env("CHUNK_SIZE", str(d.chunk_size))),
            chunk_overlap=int(env("CHUNK_OVERLAP", str(d.chunk_overlap))),
            llm_model=env("LLM_MODEL", d.llm_model),
            llm_temperature=float(env("LLM_TEMPERATURE", str(d.llm_temperature))),
            top_k=int(env("TOP_K", str(d.top_k))),
            history_max_messages=int(env("HISTORY_MAX_MESSAGES", str(d.history_max_messages))),
            lead_trigger_turn=int(env("LEAD_TRIGGER_TURN", str(d.lead_trigger_turn))),
            leads_db_path=Path(env("LEADS_DB_PATH", str(d.leads_db_path))),
            leads_json_path=Path(env("LEADS_JSON_PATH", str(d.leads_json_path))),
            admin_api_key=env("ADMIN_API_KEY", d.admin_api_key),
        )

    def with_overrides(self, **changes) -> "Settings":
        return replace(self, **changes)
