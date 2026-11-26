# Deploying to Coolify

The app ships as one Docker container. It runs the FastAPI backend and serves the demo UI at `/`.

| File | Purpose |
|---|---|
| `Dockerfile` | two-stage build: CPU-only PyTorch, dependencies, embedding model baked in |
| `docker/entrypoint.sh` | checks secrets, seeds `/data` on first start, runs uvicorn (1 worker) |
| `docker-compose.yml` | Coolify resource: env vars, persistent volume, domain |
| `.dockerignore` | keeps `env/`, `.env`, local DBs and the index out of the image |

## 1. Create the resource

1. Push this branch to your Git provider.
2. In Coolify: **New Resource → (your Git repo) → Build Pack: Docker Compose**.
   Set the compose file path to `/docker-compose.yml`.
3. Under **Environment Variables**, set:

   | Variable | Required | Value |
   |---|---|---|
   | `GROQ_API_KEY` | yes | your Groq key |
   | `ADMIN_API_KEY` | yes | a long random value: `openssl rand -hex 32` |
   | `LLM_MODEL` | no | default `openai/gpt-oss-20b` |
   | `TOP_K`, `LEAD_TRIGGER_TURN` | no | defaults `5`, `2` |
   | `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | no | LangSmith; tracing is off by default |

   The container refuses to start if `GROQ_API_KEY` is missing, or if `ADMIN_API_KEY` is missing
   or still `admin_secret_key_123`.
4. Under the service's **Domains**, set your domain, e.g. `https://chat.example.com`.
   Coolify routes it to container port 8000 and handles TLS.
5. Deploy.

The Dockerfile build pack also works: set **Port** to `8000`, then add a persistent storage
mount at `/data` under **Storages**. Without that mount, data is lost on every redeploy.

## 2. What happens on first start

All runtime data lives in the `chatbot-data` volume mounted at `/data`:

```
/data/knowledge/    documents (seeded from the repo's knowledge/ on first start; uploads go here)
/data/chroma_db/    vector index (built automatically if empty)
/data/leads.db      leads
/data/leads.json    leads mirror
```

- **Empty `/data/knowledge`:** the documents bundled in the image are copied in.
- **Empty `/data/chroma_db`:** the index is built with `python main.py --ingest`. Expect about a
  minute on a small server; the health check allows 120 s for startup.
- **Redeploys** keep the volume, so uploads, the index and leads survive.

  Editing `knowledge/` in the repo does **not** change an existing deployment. Upload files
  through the admin UI instead, or run `POST /api/admin/reindex` after changing `/data/knowledge`.

## 3. Checks after deploy

```bash
curl https://chat.example.com/api/health          # status, model, chunk count, documents
open https://chat.example.com/                    # demo UI
open https://chat.example.com/docs                # Swagger
```

The admin panel in the UI needs the new `ADMIN_API_KEY`. The page pre-fills the old default
key, so paste the new one in.

## 4. Server sizing and limits

- **RAM:** about 1 GB for PyTorch, the MiniLM model and Chroma. Give the container at least 1.5 GB.
- **One worker, one replica:** chat sessions are kept in process memory. Running more workers
  or replicas would split a visitor's conversation between processes. Sessions also reset on
  every redeploy or restart (leads and the index do not).
- **Image size:** about 1.5 GB, mostly CPU PyTorch.

## 5. Run the image locally (optional)

```bash
docker build -t jibb-chatbot .
docker run --rm -p 8000:8000 \
  -e GROQ_API_KEY=gsk_... -e ADMIN_API_KEY=$(openssl rand -hex 32) \
  -v chatbot-data:/data jibb-chatbot
# http://localhost:8000
```

## 6. Embed the chat widget on a website

Add one tag to any page, just before `</body>` (on a Next.js site, put it in the root layout):

```html
<script src="https://chat.example.com/widget.js" defer></script>
```

Replace `chat.example.com` with the domain set in step 1.4. The widget reads its API address
from its own `src`, so nothing else needs configuring. It renders in a Shadow DOM, so site CSS
can't affect it, and it follows the site's dark mode (`class="dark"` on `<html>`).

Optional attributes: `data-lang="ja"` (Japanese UI; also detected from `<html lang>` or a `/ja/`
path), `data-position="left"`, `data-open="true"`.

To try it, open `https://chat.example.com/widget-demo`.
