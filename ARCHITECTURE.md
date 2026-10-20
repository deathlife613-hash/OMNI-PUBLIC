# OMNI Architecture

```
Browser (React/TS)  ──HTTPS──►  FastAPI backend  ──►  SQLite (now) / Postgres (Phase 8)
 never holds model keys           holds all secrets    └─►  Hosted model API (Groq, …)
```

Four independent layers, each swappable through environment variables:

| Layer | Now | Replaceable by |
|---|---|---|
| Frontend | React + TypeScript + Vite (static files) | Any static host (Cloudflare Pages, etc.) |
| Backend | FastAPI + Pydantic | Any container/VM host (Dockerfile) |
| Storage | SQLite with versioned migrations (`app/core/db.py`) | Postgres adapter (Phase 8) |
| AI brain | Provider adapter (Phase 2) | Groq / Ollama Cloud / OpenRouter / local |

**Hosting vs. brain:** hosting runs OMNI's *code* (web server, database). The brain is a remote model API that OMNI's backend calls. Your computer needs only a browser. Claude is never in the runtime path.

## Backend layout (`backend/app`)
- `core/` config (env), db (migrations) — `api/` routes — `security/` auth
- `models/` (provider adapters), `services/`, `memory/`, `tools/` — empty until their phases

## Rules baked in
- Secrets only in backend env; `/api/status` returns booleans, never values.
- `/api/health` is public and minimal; everything else needs the owner token. Production without a token fails closed (503).
- Unknown metrics are `null` → UI shows "Unavailable". Nothing is simulated.
- Single deployable unit: the backend serves the built frontend when `frontend/dist` exists.

## Planned (not built)
Provider router (P2) · memory & export (P3) · voice (P4) · tools (P5) · web search (P6) · hosting (P8) · bounded agents, coding workspace, approved skills (P9–10).
