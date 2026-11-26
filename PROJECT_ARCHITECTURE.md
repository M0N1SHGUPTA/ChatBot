# JIBB RAG ChatBot: Architecture

A retrieval-augmented chatbot for JIBB (Japan India Business Bureau). A FastAPI backend runs two
pipelines: **ingestion** (knowledge files → chunks → Chroma) and **retrieval** (question → relevant
chunks → Groq answer). On top of that it has conversational lead capture, an admin API and an
evaluation harness. Diagrams: `PROJECT_FLOW.md`.

---

## Layout

```
app/
  config.py              Settings.from_env(): the only place env vars are read
  models.py              shared dataclasses: Document, Message, Lead, Answer, StreamEvent, ChatResult…
  container.py           build(settings): creates every component once and wires them together

  ingestion/             PIPELINE 1: files → index
    loaders.py           DocumentLoader: pdf / docx / txt / md → Document
    splitter.py          TextSplitter: RecursiveCharacterTextSplitter (1800 / 300)
    pipeline.py          IngestionPipeline: reindex, upload, delete, list_documents

  vectorstore/           shared by both pipelines
    embeddings.py        HFEmbedder: all-MiniLM-L6-v2 on CPU, loaded on first use
    chroma.py            ChromaStore: persistent collection, deterministic chunk ids

  retrieval/             PIPELINE 2: question → answer
    prompts.py           rewrite + answer prompts
    pipeline.py          RetrievalPipeline: history-aware rewrite → top-k search → Groq answer

  chat/
    sessions.py          SessionStore: per-session history (12-message window), turns, lead draft
    service.py           ChatService: the one path every visitor message takes

  leads/
    catalog.py           the 8 JIBB services
    texts.py             fixed lead-flow replies
    flow.py              LeadFlow: extract name / email / service, store complete leads
    store.py             LeadStore: SQLite leads table (+ leads.json mirror)

  api/                   FastAPI
    main.py              create_app(container)
    routers/             chat.py · admin.py · leads.py · system.py
    schemas.py           request / response models
    deps.py              container access, admin-key check
  cli.py                 python main.py …

api.py, main.py          entry points (`uvicorn api:app`, `python main.py`)
knowledge/               knowledge-base documents only (everything here is indexed)
static/index.html        demo admin dashboard + chat UI
evals/                   golden set, lead dialogues, judge, metrics, runner, results
tests/                   pytest suite (fakes in tests/fakes.py; no network or model)
```

Rules, checked by `tests/test_architecture.py`:
- `ingestion/` and `retrieval/` never import each other.
- No pipeline, nor `chat/` or `leads/`, imports `api/`, `cli.py` or `container.py`.
- `models.py` uses the standard library only.

Importing a module never does work: no DB creation and no model load at import time.

---

## How the API calls the pipelines

```
                       ┌──────────── FastAPI (app/api) ─────────────┐
 POST /api/admin/upload │                                            │ POST /api/chat
 POST /api/admin/reindex├─▶ IngestionPipeline        ChatService ◀───┤ POST /api/chat/stream
 DELETE /api/admin/docs │     load → split → store     │  ▲          │
                       └──────────────┬───────────────┼──┼──────────┘
                                      ▼               ▼  │
                                  ChromaStore ◀── RetrievalPipeline ──▶ Groq
                                  (+ HFEmbedder)       LeadFlow ──▶ LeadStore (SQLite)
```

### One chat message

```
POST /api/chat  ─▶ routers/chat.py ─▶ ChatService.ahandle_message(session_id, text)
   1. SessionStore.increment_turns          → turn_count
   2. LeadFlow.is_active                    → trigger_lead_capture (turn ≥ LEAD_TRIGGER_TURN, no lead yet)
   3. LeadFlow.process(text)                → message has name/email/service? reply from leads/texts.py,
                                              store the lead when complete
   4. otherwise RetrievalPipeline.aanswer(text, SessionStore.history)
        rewrite follow-up → Chroma top-5 → Groq answer with context
   5. SessionStore.append(user, assistant)
```

`/api/chat/stream` runs the same steps through `ChatService.start_stream()`. The CLI and the eval
runner call `handle_message()`.

### Ingestion

`IngestionPipeline.reindex()` → `DocumentLoader.load_dir(knowledge/)` → `TextSplitter.chunk` →
`ChromaStore.replace_all` → `RetrievalPipeline.reload()`. An upload indexes one file with
`ChromaStore.add`. Chunk ids are `source:page:n`, so re-uploading a file replaces its chunks
instead of duplicating them.

---

## HTTP API (used by `static/index.html`)

| Endpoint | Purpose |
|---|---|
| `GET /` | demo page |
| `GET /api/health` | model, chunk count, document names |
| `POST /api/chat` | answer as JSON |
| `POST /api/chat/stream` | answer as Server-Sent Events |
| `POST /api/chat/clear` | clear a session's history |
| `GET /api/services` | the 8 services |
| `POST /api/leads` | lead form |
| `POST /api/admin/upload` 🔑 | upload + index files |
| `GET /api/admin/documents` 🔑 | list files and chunk counts |
| `DELETE /api/admin/documents/{filename}` 🔑 | remove a file and its chunks |
| `POST /api/admin/reindex` 🔑 | rebuild the index |
| `GET /api/admin/leads` 🔑 | list leads |

🔑 = `X-Admin-API-Key` header. Full request/response details: `API_DOCUMENTATION.md`.

---

## Changing a component

| To change | Edit |
|---|---|
| Prompt wording | `app/retrieval/prompts.py` |
| Answer pipeline (e.g. Groq SDK without LangChain) | `app/retrieval/pipeline.py`, keeping `answer` / `aanswer` / `astream` / `reload` |
| Embedding model | `EMBEDDING_MODEL`, or `app/vectorstore/embeddings.py`; then reindex |
| Vector DB | `app/vectorstore/chroma.py`, keeping `add` / `replace_all` / `delete_source` / `stats` / `search`; then reindex |
| Chunking | `CHUNK_SIZE` / `CHUNK_OVERLAP`, or `app/ingestion/splitter.py`; then reindex |
| Session storage (SQLite, Redis) | `app/chat/sessions.py` |

To use a different implementation, pass it to `build()` in `app/container.py`. Tests swap in
fakes the same way: `build(settings, embedder=HashEmbedder(), retrieval=FakeRetrieval())`.

---

## Technology

| Concern | Technology |
|---|---|
| LLM | Groq, `openai/gpt-oss-20b` (`LLM_MODEL`) |
| Orchestration | LangChain chains inside `app/retrieval/pipeline.py` only |
| Embeddings | `all-MiniLM-L6-v2`, local CPU (`EMBEDDING_MODEL`) |
| Vector store | ChromaDB in `./chroma_db` (`CHROMA_PATH`) |
| Parsing | pypdf, docx2txt, TextLoader |
| API | FastAPI + uvicorn |
| Leads | SQLite `leads.db` (+ `leads.json`) |
| Observability | LangSmith, if `LANGCHAIN_TRACING_V2=true` |

---

## Configuration

All settings live in `app/config.py` and can be overridden by environment variables (or `.env`):

`GROQ_API_KEY`, `ADMIN_API_KEY`, `KNOWLEDGE_DIR`, `CHROMA_PATH`, `CHROMA_COLLECTION`,
`EMBEDDING_MODEL`, `HF_HUB_OFFLINE`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `LLM_MODEL`, `LLM_TEMPERATURE`,
`TOP_K`, `HISTORY_MAX_MESSAGES`, `LEAD_TRIGGER_TURN`, `LEADS_DB_PATH`, `LEADS_JSON_PATH`,
`STATIC_DIR`, and LangSmith's `LANGCHAIN_*`.

---

## Running

```bash
source env/bin/activate
python main.py --ingest                 # rebuild the index from knowledge/
python main.py --query "Where is the Tokyo office?"
python main.py --chat                   # interactive, with lead capture
python main.py --serve                  # API + demo UI on :8000  (or: uvicorn api:app)
pytest                                  # tests (offline)
python -m evals.run --label <name>      # evals (calls Groq)
```

Roadmap and status: `IMPLEMENTATION_PLAN.md`. Findings behind it: `AUDIT.md`.
