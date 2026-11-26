# JIBB RAG ChatBot: Flow Diagrams

Diagrams of how the project is built and how requests move through it. Each diagram is in Mermaid,
which GitHub, VS Code (with a Mermaid extension) and most Markdown viewers render.

**What it is:** a FastAPI backend that runs two pipelines. The **ingestion pipeline** turns the
documents in `knowledge/` into searchable chunks in Chroma. The **retrieval pipeline** answers a
visitor's question from those chunks with a Groq LLM. Around them: conversational lead capture,
an admin API for the knowledge base, a demo UI and an evaluation harness.

---

## 1. System overview

```mermaid
flowchart LR
    subgraph Clients
        UI["Demo UI<br/>static/index.html"]
        A["Admin<br/>(X-Admin-API-Key)"]
        CLI["CLI<br/>python main.py"]
        EV["Eval runner<br/>evals/run.py"]
    end

    subgraph Backend["FastAPI backend (app/)"]
        API["app/api<br/>chat · admin · leads · system"]
        ING["Ingestion pipeline<br/>app/ingestion"]
        CHAT["ChatService<br/>app/chat"]
        RET["Retrieval pipeline<br/>app/retrieval"]
        LF["Lead flow<br/>app/leads"]
    end

    subgraph Storage
        KB[("knowledge/<br/>.md .pdf .docx .txt")]
        CH[("Chroma<br/>chroma_db/")]
        LDB[("leads.db<br/>+ leads.json")]
        MEM[("In-memory<br/>sessions")]
    end

    subgraph External
        HF["HuggingFace<br/>all-MiniLM-L6-v2 (local CPU)"]
        GROQ["Groq LLM<br/>openai/gpt-oss-20b"]
    end

    UI --> API
    A --> API
    API -->|upload / reindex / delete| ING
    API -->|chat / stream| CHAT
    CLI --> ING
    CLI --> CHAT
    EV --> CHAT

    ING --> KB
    ING --> CH
    CHAT --> LF
    CHAT --> RET
    CHAT --> MEM
    LF --> LDB
    RET --> CH
    RET --> GROQ
    CH -. embeddings .-> HF
```

---

## 2. Code layout

`app/container.py` builds every component once and hands them to the API and CLI.
`tests/test_architecture.py` fails if the two pipelines import each other, or if any
lower module imports the API.

```mermaid
flowchart TB
    EP["api.py · main.py<br/>entry points"]
    API["app/api/<br/>main.py · routers/ · schemas.py · deps.py"]
    CLI["app/cli.py"]
    CT["app/container.py<br/>build(settings)"]
    CFG["app/config.py<br/>Settings.from_env()"]

    subgraph P1["app/ingestion/"]
        LO[loaders.py<br/>DocumentLoader]
        SP[splitter.py<br/>TextSplitter]
        IP[pipeline.py<br/>IngestionPipeline]
    end
    subgraph VS["app/vectorstore/"]
        EM[embeddings.py<br/>HFEmbedder]
        CS[chroma.py<br/>ChromaStore]
    end
    subgraph P2["app/retrieval/"]
        PR[prompts.py]
        RP[pipeline.py<br/>RetrievalPipeline]
    end
    subgraph CH["app/chat/"]
        SS[sessions.py<br/>SessionStore]
        SV[service.py<br/>ChatService]
    end
    subgraph LD["app/leads/"]
        FL[flow.py<br/>LeadFlow]
        ST[store.py<br/>LeadStore]
        CA[catalog.py · texts.py]
    end
    MD["app/models.py<br/>shared dataclasses"]

    EP --> API
    EP --> CLI
    API --> CT
    CLI --> CT
    CT --> CFG
    CT --> IP
    CT --> RP
    CT --> SV
    IP --> LO
    IP --> SP
    IP --> CS
    RP --> CS
    RP --> PR
    CS --> EM
    SV --> SS
    SV --> FL
    FL --> ST
    FL --> CA
```

---

## 3. One chat message, end to end

The same `ChatService` handles every message, whether it comes from the API, the stream endpoint,
the CLI or the eval runner.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Router (/api/chat)
    participant CS as ChatService
    participant SS as SessionStore (memory)
    participant LF as LeadFlow
    participant LS as LeadStore (SQLite)
    participant RP as RetrievalPipeline
    participant VS as Chroma
    participant G as Groq LLM

    C->>R: POST {session_id, message}
    R->>CS: ahandle_message(session_id, text)
    CS->>SS: increment_turns()
    SS-->>CS: turn_count
    CS->>LF: is_active()? (turn >= 2 and no lead stored)
    CS->>LF: process(text)
    LF->>LF: regex: name / email / service?

    alt message carries lead details
        LF->>SS: merge into lead draft
        opt draft complete (name + email + service)
            LF->>LS: save lead
        end
        LF-->>CS: LeadReply (fixed text from leads/texts.py)
    else no lead details
        LF-->>CS: None
        CS->>SS: history() (last 12 messages)
        CS->>RP: aanswer(text, history)
        RP->>G: rewrite follow-up into a standalone question
        RP->>VS: similarity search, top 5 chunks
        VS-->>RP: chunks + sources
        RP->>G: answer prompt + context + history
        G-->>RP: answer text
        RP-->>CS: Answer(text, context)
    end

    CS->>SS: append(user, assistant)
    CS-->>R: ChatResult
    R-->>C: {answer, sources, message_count, trigger_lead_capture, services}
```

### Decision view of the same flow

```mermaid
flowchart TD
    M[Visitor message] --> T[Count turn]
    T --> Q1{"Lead capture active?<br/>turn >= LEAD_TRIGGER_TURN<br/>and no lead for session"}
    Q1 -- no --> RAG
    Q1 -- yes --> X{"Message contains<br/>name / email / service?"}
    X -- no --> RAG
    X -- yes --> DR[Merge fields into lead draft]
    DR --> CP{Draft complete?}
    CP -- yes --> SAVE[(Save lead to leads.db)] --> LR1[Reply: thank-you text]
    CP -- no --> LR2[Reply: ask for missing field]
    RAG["Retrieval pipeline<br/>rewrite → top 5 chunks → Groq"] --> H
    LR1 --> H
    LR2 --> H
    H[Save exchange in session history] --> OUT[Return answer + trigger_lead_capture flag]
```

---

## 4. Streaming (`POST /api/chat/stream`, used by the UI)

```mermaid
sequenceDiagram
    participant C as Browser
    participant R as Router
    participant CS as ChatService
    participant RP as RetrievalPipeline

    C->>R: POST message
    R->>CS: start_stream(session_id, text)
    CS-->>R: ChatStream (turn, trigger, lead_reply?)
    alt lead reply
        R-->>C: SSE {"token": word} per word
    else RAG
        R->>RP: astream(question, history)
        loop each token
            RP-->>R: context / token events
            R-->>C: SSE {"token": "..."}
        end
        Note over CS: history saved only after the full answer has streamed
    end
    R-->>C: SSE {"sources", "session_id", "message_count", "trigger_lead_capture", "done": true}
    Note over R,C: on failure: {"error", "done": true}
```

---

## 5. Ingestion pipeline

```mermaid
flowchart LR
    subgraph AdminAPI ["/api/admin (X-Admin-API-Key)"]
        UP[POST /upload]
        RI[POST /reindex]
        DEL["DELETE /documents/{filename}"]
        LS[GET /documents]
    end

    UP --> SAVE["Save file to knowledge/"]
    SAVE --> L1[DocumentLoader.load_file]
    L1 --> C1[TextSplitter 1800 / 300]
    C1 --> ADD["ChromaStore.add<br/>ids = source:page:n (re-upload upserts)"]

    RI --> L2["DocumentLoader.load_dir(knowledge/)"]
    L2 --> C2[TextSplitter]
    C2 --> REP[ChromaStore.replace_all]

    DEL --> RM[Remove file + its chunks]
    LS --> STATS[Files on disk + chunk counts]

    ADD --> EMB[HFEmbedder MiniLM]
    REP --> EMB
    EMB --> CH[(Chroma)]
    REP --> RL[RetrievalPipeline.reload]
```

CLI equivalent: `python main.py --ingest`.

---

## 6. Retrieval pipeline

```mermaid
flowchart LR
    Q[Question] --> HAS{History<br/>empty?}
    H[(Last 12 messages)] --> RW
    HAS -- no --> RW["Groq: rewrite into a<br/>standalone question<br/>(CONTEXTUALIZE_PROMPT)"]
    HAS -- yes --> SQ
    RW --> SQ[Standalone question]
    SQ --> E[HFEmbedder.embed_query]
    E --> S["Chroma similarity search<br/>top k = 5"]
    S --> CTX[Context chunks]
    CTX --> ANS["Groq: answer<br/>(ANSWER_PROMPT + context + history)"]
    Q --> ANS
    H --> ANS
    ANS --> OUT["Answer text + source chunks<br/>(or token stream)"]
```

---

## 7. Data model

```mermaid
erDiagram
    LEADS {
        int id PK
        text session_id
        text name
        text email
        text service
        text notes
        text created_at
    }
    SESSION_MEMORY {
        string session_id
        list history "last 12 messages"
        int turns
        dict lead_draft
    }
    CHROMA_CHUNK {
        string id "source:page:n"
        string text
        vector embedding "MiniLM 384-d"
        string source
    }
    SESSION_MEMORY ||--o| LEADS : "produces at most one"
```

`LEADS` lives in `leads.db` (mirrored to `leads.json`), sessions in process memory, chunks in
`chroma_db/`.

---

## 8. API map

```mermaid
flowchart LR
    ROOT((FastAPI app))

    ROOT --> SYS[system]
    SYS --> S1["GET /  (demo page)"]
    SYS --> S2[GET /api/health]

    ROOT --> CHAT["chat (/api/chat)"]
    CHAT --> C1[POST /api/chat]
    CHAT --> C2[POST /api/chat/stream]
    CHAT --> C3[POST /api/chat/clear]

    ROOT --> LEADS["leads (/api)"]
    LEADS --> L1[GET /api/services]
    LEADS --> L2["POST /api/leads (form)"]

    ROOT --> ADM["admin (/api/admin) 🔑"]
    ADM --> A1[POST /upload]
    ADM --> A2[GET /documents]
    ADM --> A3["DELETE /documents/{filename}"]
    ADM --> A4[POST /reindex]
    ADM --> A5[GET /leads]
```

🔑 = needs the `X-Admin-API-Key` header.

---

## 9. Evaluation loop

```mermaid
flowchart LR
    G[evals/golden.jsonl<br/>Q&A from knowledge files] --> RUN[evals/run.py]
    LD[evals/lead_dialogues.jsonl] --> RUN
    RUN --> ADP[evals/adapter.py<br/>builds a container]
    ADP --> CS[ChatService.handle_message]
    CS --> OUT[Answers + sources]
    OUT --> J["judge.py<br/>LLM faithfulness judge"]
    OUT --> MET["metrics.py<br/>retrieval + lead metrics"]
    J --> RES[(evals/results/*.json)]
    MET --> RES
    RES --> CMP[Compare with baseline.json<br/>before / after each change]
```

---

## 10. Project status

```mermaid
flowchart LR
    M0[M0 audit + evals] --> A1[A1 lead parser fix] --> R["R modular refactor"] --> P["P pipeline layout"] --> A2["A2 next:<br/>replace LangChain chains"]
    A2 --> A4["A4 multilingual embeddings"]
    A2 --> B1["B1 SQLite sessions"]
    A2 --> W["Embed widget<br/>(later)"]

    classDef done fill:#d1fae5,stroke:#059669,color:#064e3b
    classDef todo fill:#e5e7eb,stroke:#6b7280,color:#111827
    class M0,A1,R,P done
    class A2,A4,B1,W todo
```

Known gaps (from `AUDIT.md`): the embeddings are English-only, so Japanese retrieval is poor;
chunks are longer than MiniLM reads; there is no relevance threshold; the lead parser is
regex-based; sessions live in memory, so they are lost on restart and not shared between workers.
