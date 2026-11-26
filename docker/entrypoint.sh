#!/bin/sh
# Container start: check secrets, prepare /data on first run, then start the API.
set -e

# --- secrets ---------------------------------------------------------------------------------
if [ -z "$GROQ_API_KEY" ]; then
    echo "ERROR: GROQ_API_KEY is not set. Please set GROQ_API_KEY in Coolify environment variables." >&2
    exit 1
fi
if [ -z "$ADMIN_API_KEY" ]; then
    echo "WARNING: ADMIN_API_KEY is not set. Defaulting to admin_secret_key_123." >&2
    export ADMIN_API_KEY="admin_secret_key_123"
elif [ "$ADMIN_API_KEY" = "admin_secret_key_123" ]; then
    echo "WARNING: Running with default ADMIN_API_KEY. For production, set a strong random value." >&2
fi

# --- first run: seed the knowledge folder and build the index ---------------------------------
mkdir -p "$KNOWLEDGE_DIR" "$CHROMA_PATH"

if [ -z "$(ls -A "$KNOWLEDGE_DIR")" ]; then
    echo "Seeding $KNOWLEDGE_DIR with the documents shipped in the image..."
    cp -r /app/seed-knowledge/. "$KNOWLEDGE_DIR/"
fi

if [ -z "$(ls -A "$CHROMA_PATH")" ]; then
    echo "No vector index found in $CHROMA_PATH; indexing $KNOWLEDGE_DIR..."
    python main.py --ingest || echo "WARNING: indexing failed; upload documents or POST /api/admin/reindex."
fi

# --- serve -----------------------------------------------------------------------------------
# One worker: chat sessions are kept in process memory and would not be shared between workers.
# Proxy headers: Coolify's reverse proxy (Traefik/Caddy) terminates TLS in front of the container.
exec uvicorn api:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips "*"
