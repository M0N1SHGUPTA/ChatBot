import io
import json

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app

ADMIN = {"X-Admin-API-Key": "test-admin-key"}


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def test_get_services(client):
    data = client.get("/api/services").json()
    assert data["total_services"] == 8
    assert "Market Landscaping" in data["services"]


def test_submit_lead(client):
    bad = client.post("/api/leads", json={"session_id": "t", "name": "Bob", "email": "not-an-email",
                                          "service": "Market Landscaping"})
    assert bad.status_code == 422
    ok = client.post("/api/leads", json={"session_id": "t", "name": "Bob", "email": "Bob@X.com",
                                         "service": "Market Landscaping"})
    assert ok.status_code == 201 and ok.json()["lead"]["email"] == "bob@x.com"
    leads = client.get("/api/admin/leads", headers=ADMIN).json()
    assert leads["total_leads"] == 1


def test_admin_auth_protection(client):
    assert client.get("/api/admin/leads").status_code == 401
    assert client.get("/api/admin/leads", headers={"X-Admin-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/admin/documents", headers=ADMIN).status_code == 200


def test_chat_endpoint(client):
    r1 = client.post("/api/chat", json={"session_id": "v1", "message": "What is JIBB?"}).json()
    assert r1["answer"] == "ANSWER: What is JIBB?" and r1["sources"] == ["site.md"]
    assert r1["message_count"] == 1 and r1["trigger_lead_capture"] is False and r1["services"] is None
    r2 = client.post("/api/chat", json={"session_id": "v1", "message": "More?"}).json()
    assert r2["trigger_lead_capture"] is True and len(r2["services"]) == 8


def _events(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_chat_stream_rag_and_lead(client):
    ev = _events(client.post("/api/chat/stream", json={"session_id": "v2", "message": "hi"}))
    assert "".join(e.get("token", "") for e in ev).strip() == "ANSWER: hi"
    assert ev[-1]["done"] and ev[-1]["sources"] == ["site.md"] and ev[-1]["message_count"] == 1
    client.post("/api/chat/stream", json={"session_id": "v2", "message": "second"})
    ev = _events(client.post("/api/chat/stream", json={"session_id": "v2", "message": "My name is Ana Lima"}))
    assert "Ana Lima" in "".join(e.get("token", "") for e in ev)
    assert ev[-1]["trigger_lead_capture"] is True and ev[-1]["sources"] == []


def test_clear_endpoint(client, container):
    client.post("/api/chat", json={"session_id": "v3", "message": "hi"})
    assert client.post("/api/chat/clear", json={"session_id": "v3"}).json()["status"] == "success"
    assert container.sessions.history("v3") == []


def test_document_lifecycle(client, retrieval):
    up = client.post("/api/admin/upload", headers=ADMIN, files=[
        ("files", ("kb.md", io.BytesIO(b"# Offices\n\nTokyo office is in Akasaka."), "text/markdown")),
        ("files", ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")),
    ]).json()
    assert up["total_chunks_added"] == 1
    assert [f["status"] for f in up["files"]] == ["success", "error"]

    docs = client.get("/api/admin/documents", headers=ADMIN).json()
    assert docs["documents"][0]["filename"] == "kb.md" and docs["documents"][0]["chunks_in_db"] == 1

    health = client.get("/api/health").json()
    assert health["total_chunks"] == 1 and health["documents"] == ["kb.md"]

    re = client.post("/api/admin/reindex", headers=ADMIN).json()
    assert re["status"] == "success" and retrieval.reloads == 1

    assert client.delete("/api/admin/documents/kb.md", headers=ADMIN).status_code == 200
    assert client.delete("/api/admin/documents/kb.md", headers=ADMIN).status_code == 404
    assert client.get("/api/health").json()["total_chunks"] == 0


def test_demo_page(client):
    assert client.get("/").status_code == 200


def test_widget_script_served_cross_origin(client):
    r = client.get("/widget.js", headers={"Origin": "https://npo-jibb.org"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert r.headers["access-control-allow-origin"] in ("*", "https://npo-jibb.org")
    assert "/api/chat/stream" in r.text and "attachShadow" in r.text


def test_widget_demo_page_embeds_script(client):
    r = client.get("/widget-demo")
    assert r.status_code == 200 and "/widget.js" in r.text


def test_chat_stream_allows_cross_origin(client):
    r = client.post("/api/chat/stream", json={"message": "hi", "session_id": "w_x"},
                    headers={"Origin": "https://npo-jibb.org"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in ("*", "https://npo-jibb.org")
