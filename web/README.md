# NewsAgreator web

Minimal Next.js UI for the FastAPI brief pipeline.

## Run

Start the API from `app/server`. `make run` uses the project venv, dev mode and CUDA on port 8012:

```bash
cd ../server
make run
```

Or manually, in one line:

```bash
NEWS_APP_ENV=dev NEWS_LAYA_DEVICE=cuda uv run uvicorn main:app --port 8012
```

Use `make run LAYA_DEVICE=cpu` or `make run PORT=8013` to change the device/port. A bare `uvicorn`
command only works after activating `.venv`.

Then start the web app:

```bash
bun install
bun dev
```

Open <http://localhost:3000>, enter a query, and the page streams pipeline stages and renders the
brief, facts, stories and coverage.

The API base defaults to `http://localhost:8012`. Override it with:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8013 bun dev
```

The server's CORS default allows `http://localhost:3000`. If the web app runs on another port, set
`NEWS_CORS_ORIGINS` in `app/server/.env`.

Checks:

```bash
bun run lint
bun run build
```
