# NewsAgreator app

One command runs the whole stack:

```bash
python app/start.py
```

From inside `app/`, the equivalent is:

```bash
python start.py
```

`start.py` is the single, cross-platform entrypoint. It checks the toolchain, creates
`server/.env` from the example when missing, syncs both environments, starts the FastAPI API and
the Next.js web app, waits for both to become ready, and stops both cleanly. Linux, macOS and
Windows are supported.

## Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Python 3.10+ | the launcher itself | `python --version` |
| [uv](https://docs.astral.sh/uv/) | server dependencies and `uvicorn` | `uv --version` |
| [bun](https://bun.sh/docs/installation) | web dependencies and `next dev` | `bun --version` |

The server project asks for Python 3.13; `uv` resolves and installs the right interpreter during
`uv sync`, so a system Python 3.13 is not required for the server.

Install the tools:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.sh/install | bash
```

```powershell
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
powershell -c "irm bun.sh/install.ps1 | iex"
```

Reopen the shell after installing so `uv` and `bun` are on `PATH`. The launcher resolves both with
`shutil.which`, runs `--version`, and fails fast with the install link if either is missing or not
runnable.

## What the launcher does

1. Verifies `uv` and `bun` exist and execute.
2. Verifies `app/server/main.py` and `app/web/package.json` are present.
3. Refuses to start if the API or web port is already in use.
4. Creates `app/server/.env` from `app/server/.env.example` if it does not exist.
5. Runs these in parallel:
   - `uv sync --extra laya` in `app/server`
   - `bun install` in `app/web`
6. Starts:
   - API: `uv run uvicorn main:app --host 127.0.0.1 --port 8012`
   - Web: `bun run dev -- --port 3000`

It injects `NEWS_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` into the child processes so custom
ports keep working without editing `.env`. It probes:

- API readiness: `http://127.0.0.1:8012/ready`
- Web readiness: `http://localhost:3000/`

Press `Ctrl+C` to stop both. On POSIX the launcher signals the process groups; on Windows it sends
a console break and falls back to `taskkill /T /F` so `uv` and Node children do not survive.

## URLs

| Service | URL |
|---|---|
| Web chat | <http://localhost:3000> |
| API health | <http://127.0.0.1:8012/health> |
| API readiness | <http://127.0.0.1:8012/ready> |
| Chat stream | `POST http://127.0.0.1:8012/api/v1/chat/stream` |
| One-shot brief stream | `POST http://127.0.0.1:8012/api/v1/brief/stream` |

## Options

```bash
python app/start.py --help
```

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | API bind host |
| `--port` | `8012` | API port |
| `--web-port` | `3000` | Next.js port |
| `--device` | from `.env` | Laya device: `cuda` or `cpu` |
| `--app-env` | `dev` | API mode: `dev`, `demo` (fixtures/heuristic, offline), or `prod` |
| `--no-sync` | off | Skip `uv sync` and `bun install` |
| `--plain` | off | Stream prefixed logs instead of the TUI |
| `--tui` | auto | Force the curses TUI when available |

Examples:

```bash
# Custom ports
python app/start.py --port 8013 --web-port 3001

# Fast restart when dependencies are already installed
python app/start.py --plain --no-sync

# CPU-only Laya
python app/start.py --device cpu

# Offline/demo data
python app/start.py --app-env demo
```

## OS notes

### Linux / macOS

- Interactive terminals use the curses TUI by default.
- Use `--plain` for prefixed, line-oriented logs in a normal terminal or a log collector.
- If the terminal is not interactive, `TERM` is `dumb`, or curses fails, the launcher automatically
  falls back to plain logs.
- Stopping uses `SIGTERM` on the process group, then `SIGKILL` after 8 seconds.

### Windows

- Plain logs are the default; the TUI requires the optional `windows-curses` package and `--tui`.
- `.cmd` / `.bat` shims are launched through `cmd.exe /d /s /c` so npm-installed tools work.
- Each service gets a new process group. On stop, the launcher sends `CTRL_BREAK_EVENT` and then
  uses `taskkill /PID <pid> /T /F` if the tree has not exited after 8 seconds.
- Use `python` or `py -3` depending on how Python is installed.

## Dependencies and sync

- `uv sync --extra laya` installs the server plus the optional Laya/Torch stack.
- `bun install` installs the web dependencies.
- `--no-sync` skips both steps; use it after the first successful sync or when working offline.
- If the Laya/Torch install is not wanted, run `uv sync` manually in `app/server` (without
  `--extra laya`), then start with `--no-sync`. The server falls back to its heuristic decision
  engine when Laya is unavailable.
- The live configuration lives in `app/server/.env`. The launcher only creates it from
  `.env.example` when it is missing; it does not overwrite edits.
- `NEXT_PUBLIC_API_BASE_URL` and CORS are added by the launcher. You do not need to set them for
  the normal single-command flow.

## Troubleshooting

**`uv is not installed or not on PATH` / `bun is not installed or not on PATH`**
Install the missing tool with the commands above, reopen the shell, and confirm
`uv --version` / `bun --version` works.

**`uv at ... is not usable` / `bun at ... is not usable`**
The executable exists but cannot run. Reinstall it; on Windows check that the shim is not a broken
`.cmd` wrapper.

**`port 8012 is already in use` / `port 3000 is already in use`**
Another process is using the port. Use `--port` / `--web-port`, or find the process:

```bash
# Linux / macOS
lsof -i :8012
lsof -i :3000

# Windows
netstat -ano | findstr :8012
netstat -ano | findstr :3000
```

**TUI does not appear**
Use `--plain`. On Windows, install `windows-curses` and pass `--tui` if you want the pane UI.

**Server errors at startup**
Check `app/server/.env`, then run the backend checks:

```bash
cd app/server
uv run ruff check .
uv run pytest -q
```

**Web build/lint errors**

```bash
cd app/web
bun run lint
bun run build
```

**First sync is slow**
The first `uv sync --extra laya` may download Torch. Later runs are cached. Use `--no-sync` when
nothing changed.

## Layout

| Path | Role |
|---|---|
| `app/start.py` | Single cross-platform launcher; tool checks, sync, both servers, readiness |
| `app/server/` | FastAPI API, pipeline, chat orchestration, tests |
| `app/server/.env.example` | Backend configuration reference |
| `app/web/` | Next.js chat UI |
| `Docs/` | Product, design and session notes |

The launcher is standard-library Python only. It does not install Python, `uv` or `bun` itself.
