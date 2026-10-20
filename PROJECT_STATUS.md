# OMNI — Project Status

**Last updated:** 2026-10-20 · **Current phase:** 1 (Foundation) — files written, only partly verified

## Verification (PASS / FAIL / NOT TESTED)
| Check | Result |
|---|---|
| All backend Python files compile | PASS |
| DB migrations: idempotent init, tables, FK cascade, role CHECK (run directly with stdlib) | PASS |
| Backend API tests (health, status, auth, throttle; 9 tests) | **NOT TESTED** — sandbox blocked PyPI (HTTP 403 policy), FastAPI/pytest not installable |
| Backend starts with `uvicorn` | NOT TESTED |
| Frontend `npm install` / `tsc` / `vite build` | **NOT TESTED** — npm registry blocked (403) |
| Frontend ↔ backend in a browser | NOT TESTED |
| Docker build / compose | NOT TESTED |
| Any AI provider call | NOT BUILT (Phase 2) |
| Deployment anywhere | NOT DONE |

## Built in Phase 1
Repo structure · env config (`core/config.py`) · SQLite + versioned migrations (conversations/messages tables ready) · owner-token auth with fail-closed production mode and failure throttle · `/api/health` (public) and `/api/status` (authed, honest nulls) · React dashboard with login gate, status cards, disabled placeholders labeled by phase · Dockerfile/compose · dev scripts · README, ARCHITECTURE, SECURITY, `.env.example`, `docs/FREE_SERVICES_RESEARCH.md`.

## Decisions (proposed, pending your approval)
- Brain: **Groq** primary, **Ollama Cloud** backup, OpenRouter `:free` optional. Model names chosen in Phase 2 from live model lists.
- Hosting: develop locally for Phases 1–7. Online Plan A = Render free + Supabase free Postgres; Plan B = Oracle Always Free VM (card needed). Details/risks in `docs/FREE_SERVICES_RESEARCH.md`.
- Stack unchanged from the Master Build Prompt (React/TS/Vite, FastAPI, SQLite → Postgres adapter in Phase 8).

## Known gaps / bugs
- Tests above have never been run — expect small fixes on first run.
- PWA manifest/service worker not added yet.
- Throttle is per-process and keyed by client IP (shared behind proxies).
- Google/AWS/Azure/Vercel/Netlify/HF Spaces/Deno/GitHub Pages/Firebase not yet researched.

## Your actions (I can't do these)
1. Install Python 3.11+ and Node 20+; run the README steps; tell me the test/build output.
2. Create a free Groq account (no card per secondary sources) and an API key → put it in `.env` as `OMNI_AI_API_KEY` (never paste it in chat).
3. Do NOT create Render/Oracle/Supabase accounts yet; that's Phase 8.

## Next steps
1. You run `pytest` and `npm run build`; I fix what fails.
2. Phase 2: provider adapter interface, Groq adapter (OpenAI-compatible), live model list + capability test, chat endpoint with streaming, conversation persistence, quota/429 handling, "Test provider connection".
