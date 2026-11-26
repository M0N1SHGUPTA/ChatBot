from pathlib import Path

from app.config import Settings


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("TOP_K", "7")
    monkeypatch.setenv("LEAD_TRIGGER_TURN", "3")
    monkeypatch.setenv("KNOWLEDGE_DIR", "kb")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    s = Settings.from_env(load_dotenv_file=False)
    assert s.top_k == 7 and s.lead_trigger_turn == 3
    assert s.knowledge_dir == Path("kb") and s.hf_offline is False


def test_defaults_match_previous_hardcoded_values():
    s = Settings()
    assert (s.chunk_size, s.chunk_overlap, s.top_k, s.history_max_messages) == (1800, 300, 5, 12)
    assert s.llm_model == "openai/gpt-oss-20b" and s.collection_name == "chatbot_docs"
