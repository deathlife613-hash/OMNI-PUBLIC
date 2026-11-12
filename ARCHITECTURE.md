# OMNI Architecture

```
Browser (React/TS)  ──HTTPS──►  FastAPI backend  ──►  SQLite (default) / Postgres adapter (built)
 never holds model keys           holds all secrets    └─►  Hosted model API (Groq, …)
```

Postgres adapter: VERIFIED on local PostgreSQL 16 in Colab, 2026-10-21 (SQLite suite 192 passed, Postgres mode 186 passed, export/restore round-trip passed). A real Neon run is still pending.

Four independent layers, each swappable through environment variables:

| Layer | Now | Replaceable by |
|---|---|---|
| Frontend | React + TypeScript + Vite (static files) | Any static host (Cloudflare Pages, etc.) |
| Backend | FastAPI + Pydantic | Any container/VM host (Dockerfile) |
| Storage | SQLite with versioned migrations (`app/core/db.py`) | Postgres adapter (built; see above) |
| AI brain | Provider adapter (Phase 2) | Groq / Ollama Cloud / OpenRouter / local |

**Hosting vs. brain:** hosting runs OMNI's *code* (web server, database). The brain is a remote model API that OMNI's backend calls. Your computer needs only a browser. Claude is never in the runtime path.

## Backend layout (`backend/app`)
- `core/` config (env), db (migrations) — `api/` routes — `security/` auth
- `models/` (provider adapters), `services/`, `memory/`, `tools/`, `agents/`, `skills/`

## Rules baked in
- Secrets only in backend env; `/api/status` returns booleans, never values.
- `/api/health` is public and minimal; everything else needs the owner token. Production without a token fails closed (503).
- Unknown metrics are `null` → UI shows "Unavailable". Nothing is simulated.
- Single deployable unit: the backend serves the built frontend when `frontend/dist` exists.

## Built (Phases 2–11)
Provider router (P2) · memory & export (P3) · voice (P4) · tools (P5) · web search (P6) · hosting files (P8) · bounded agents, coding workspace, approved skills (P9–10) · hardening (P11). ElevenLabs TTS adapter and n8n webhook tool are built and mocked-verified; their live tests are still pending (see `PROJECT_STATUS.md`).


## Modules (as of Phase 11)
- `api/` thin routers: health, system (status), provider, chat (SSE), memory (memories/notes/export/restore), tools, search.
- `models/` provider adapters behind one interface (`openai_compat` for Groq/OpenRouter; paid models blocked by default).
- `services/` context builder (persona + relevant memories + web results + recent history within a budget), usage tracker, search adapters + cache/daily cap, memory retrieval.
- `tools/` explicit registry; schemas, timeouts, confirmation flag, audit log. No shell, no unrestricted filesystem.
- `agents/` bounded sequential manager→role engine with checkpoints, approval-gated coding workspace. `skills/` declarative skill lifecycle (propose → staged → human activation).
- Frontend: `Dashboard`, `Chat`, `Memory`, `Tools`, `Settings`, separate `voice/` module.
- Data: SQLite, versioned migrations (v3: conversations, messages, memories, notes, tasks, audit_log); Postgres adapter behind `OMNI_DATABASE_URL`.
