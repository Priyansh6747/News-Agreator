# NewsAgreator web

Next.js UI for the FastAPI news pipeline. The main screen is a multi-turn chat: the pipeline runs
as the `news_brief` tool, pipeline stages stream into the side panel, and charts/map render beside
the answer.

## Run the full stack

Use the single launcher from the repo root:

```bash
python app/start.py
```

Or from `app/`:

```bash
python start.py
```

It checks `uv` and `bun`, creates `app/server/.env` if needed, syncs the server and web
dependencies, starts the API on 8012 and this app on 3000, and stops both cleanly. See
[`../README.md`](../README.md) for prerequisites, options and Windows/macOS/Linux notes.

## Run the web alone

The API still needs to be running. From `app/server`:

```bash
uv run uvicorn main:app --port 8012
```

Then from this directory:

```bash
bun install
bun dev
```

Open <http://localhost:3000>. The normal flow uses the chat stream at
`POST /api/v1/chat/stream`; the legacy one-shot brief remains at `POST /api/v1/brief/stream`.

The API base defaults to `http://localhost:8012`. Override it with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8013 bun dev
```

The server's CORS default allows `http://localhost:3000`. If the web app runs on another port, set
`NEWS_CORS_ORIGINS` in `app/server/.env` or use the launcher, which injects it automatically.

Checks:

```bash
bun run lint
bun run build
```
