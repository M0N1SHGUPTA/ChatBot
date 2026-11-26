"""
Test isolation: lead DB/JSON env vars point at a temp dir BEFORE any project module is imported,
and every test gets its own container with temp paths and a fake retrieval pipeline/embedder, so tests never
touch production data, the real index, or the network.
"""
import hashlib
import os
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp(prefix="chatbot_tests_")
os.environ["LEADS_DB_PATH"] = str(Path(_TMP) / "leads.db")
os.environ["LEADS_JSON_PATH"] = str(Path(_TMP) / "leads.json")

PROD_FILES = [REPO_ROOT / "leads.db", REPO_ROOT / "leads.json"]


def _fingerprint():
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        for p in PROD_FILES
    }


_PROD_BEFORE = _fingerprint()


@pytest.fixture
def prod_fingerprint_before():
    return _PROD_BEFORE


@pytest.fixture
def current_prod_fingerprint():
    return _fingerprint


@pytest.fixture
def settings(tmp_path):
    from app.config import Settings

    (tmp_path / "knowledge").mkdir()
    return Settings(
        knowledge_dir=tmp_path / "knowledge",
        chroma_path=tmp_path / "chroma",
        collection_name="test_docs",
        leads_db_path=tmp_path / "leads.db",
        leads_json_path=tmp_path / "leads.json",
        static_dir=REPO_ROOT / "static",
        admin_api_key="test-admin-key",
    )


@pytest.fixture
def retrieval():
    from tests.fakes import FakeRetrieval

    return FakeRetrieval()


@pytest.fixture
def container(settings, retrieval):
    from app.container import build
    from tests.fakes import HashEmbedder

    return build(settings, embedder=HashEmbedder(), retrieval=retrieval)
