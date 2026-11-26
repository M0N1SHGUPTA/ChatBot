import pytest

from app.chat.sessions import SessionStore
from app.ingestion.loaders import DocumentLoader
from app.ingestion.splitter import TextSplitter
from app.leads.store import LeadStore
from app.models import Document, Lead
from app.vectorstore.chroma import ChromaStore, generate_chunk_ids
from tests.fakes import HashEmbedder


def test_chunker_keeps_metadata():
    doc = Document("Header 1\n\nThis is paragraph one.\n\n## Section 2\n\nThis is paragraph two.",
                   {"source": "test.txt", "page": 1})
    chunks = TextSplitter(chunk_size=50, chunk_overlap=10).chunk([doc])
    assert chunks
    for c in chunks:
        assert c.metadata["source"] == "test.txt" and c.metadata["page"] == 1
        assert "start_index" in c.metadata


def test_chunker_replaces_nbsp():
    chunks = TextSplitter().chunk([Document("a\xa0b", {"source": "x"})])
    assert chunks[0].text == "a b"


def test_generate_chunk_ids():
    chunks = [Document("A", {"source": "doc1.txt", "page": 0}), Document("B", {"source": "doc1.txt", "page": 0}),
              Document("C", {"source": "doc2.txt", "page": 1})]
    assert generate_chunk_ids(chunks) == ["doc1.txt:0:0", "doc1.txt:0:1", "doc2.txt:1:0"]


def test_file_loader(tmp_path):
    (tmp_path / "a.md").write_text("# Title\n\nHello", encoding="utf-8")
    (tmp_path / "b.txt").write_text("World", encoding="utf-8")
    (tmp_path / "c.xyz").write_text("skip", encoding="utf-8")
    loader = DocumentLoader()
    docs = loader.load_dir(tmp_path)
    assert sorted(d.text for d in docs) == ["# Title\n\nHello", "World"]
    with pytest.raises(ValueError):
        loader.load_file(tmp_path / "c.xyz")
    with pytest.raises(FileNotFoundError):
        loader.load_dir(tmp_path / "missing")


def test_chroma_store_roundtrip(tmp_path):
    store = ChromaStore(tmp_path / "db", "test_col", HashEmbedder())
    assert store.stats() == {"total_chunks": 0, "sources": {}}
    store.add([Document("tokyo office akasaka", {"source": "a.md"}), Document("noida office sector", {"source": "b.md"})])
    store.add([Document("tokyo office akasaka", {"source": "a.md"})])  # same id -> upsert, no duplicate
    assert store.stats() == {"total_chunks": 2, "sources": {"a.md": 1, "b.md": 1}}
    top = store.search("akasaka tokyo", k=1)
    assert top[0].document.source == "a.md"
    assert store.delete_source("a.md") == 1
    assert store.stats()["sources"] == {"b.md": 1}
    assert store.replace_all([Document("x", {"source": "c.md"})]) == 1
    assert store.stats()["sources"] == {"c.md": 1}


def test_memory_sessions_window():
    repo = SessionStore(max_messages=4)
    for i in range(6):
        repo.append("s", "user" if i % 2 == 0 else "assistant", str(i))
    assert [m.text for m in repo.history("s")] == ["2", "3", "4", "5"]
    assert repo.increment_turns("s") == 1 and repo.turns("s") == 1
    repo.lead_draft("s").name = "A"
    assert repo.lead_draft("s").name == "A"
    repo.clear_history("s")
    assert repo.history("s") == []


def test_lead_store(tmp_path):
    repo = LeadStore(tmp_path / "l.db", tmp_path / "l.json")
    assert not repo.exists_for_session("s1")
    saved = repo.save(Lead(session_id="s1", name="Alice", email="a@b.com", service="Market Landscaping"))
    assert saved.id == 1 and saved.created_at
    assert repo.exists_for_session("s1")
    repo.save(Lead(session_id="s2", name="Bob", email="b@b.com", service="Market Landscaping"))
    assert [l.name for l in repo.all()] == ["Bob", "Alice"]
    assert (tmp_path / "l.json").exists()
