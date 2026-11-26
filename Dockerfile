# JIBB RAG ChatBot: FastAPI backend + demo UI.
#
#   docker build -t jibb-chatbot .
#   docker run -p 8000:8000 -e GROQ_API_KEY=... -e ADMIN_API_KEY=... -v chatbot-data:/data jibb-chatbot
#
# Runtime data (vector index, leads, uploaded documents) lives in /data: mount a volume there.

ARG PYTHON_VERSION=3.12

# ---------- builder: install dependencies into a virtualenv ----------
FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
# CPU-only PyTorch first: the default wheel bundles CUDA (several GB) that this server never uses.
# requirements.txt then sees torch==2.15.0 as already satisfied.
RUN TORCH_VERSION=$(grep -E '^torch==' requirements.txt | cut -d= -f3 | cut -d' ' -f1) \
    && (pip install --index-url https://download.pytorch.org/whl/cpu "torch==${TORCH_VERSION}" || pip install "torch==${TORCH_VERSION}") \
    && pip install -r requirements.txt

# Bake the embedding model into the image so the app can run with HF_HUB_OFFLINE=1.
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/opt/hf
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ---------- runtime ----------
FROM python:${PYTHON_VERSION}-slim

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    # Runtime data on the persistent volume
    KNOWLEDGE_DIR=/data/knowledge \
    CHROMA_PATH=/data/chroma_db \
    LEADS_DB_PATH=/data/leads.db \
    LEADS_JSON_PATH=/data/leads.json \
    STATIC_DIR=/app/static \
    ANONYMIZED_TELEMETRY=False

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown app:app /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf

WORKDIR /app
COPY --chown=app:app api.py main.py ./
COPY --chown=app:app app/ app/
COPY --chown=app:app static/ static/
# Seed documents: copied into /data/knowledge on first start (see entrypoint)
COPY --chown=app:app knowledge/ seed-knowledge/
COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
