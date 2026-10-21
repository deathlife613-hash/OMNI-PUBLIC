# OMNI — Project Status

**Last updated:** 2026-10-20 · **Current phase:** 1 (Foundation) — backend tests and frontend build verified on Google Colab

## Verification (PASS / FAIL / NOT TESTED)
| Check | Result |
|---|---|
| All backend Python files compile | PASS |
| DB migrations: idempotent init, tables, FK cascade, role CHECK (run directly with stdlib) | PASS |
| Backend tests (health, status, auth, throttle, DB; 11 tests), Python 3.13, run on Google Colab 2026-10-20 | PASS (11 passed in 0.53s) |
| Backend starts with `uvicorn` | NOT TESTED |
| Frontend `npm install`, `tsc --noEmit`, `vite build` (Vite 5.4.21), run on Google Colab 2026-10-20 | PASS (32 modules, built in 1.63s) |
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
- GitHub Actions cannot run: the GitHub account reports a billing lock. Tests were run on Colab instead.
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

## Phase 2 — AI conversation (2026-10-20)

**Built:** provider adapter interface; OpenAI-compatible adapter (Groq, OpenRouter `:free` only unless `allow_paid_providers`); bounded retries (never on 429); SSE streaming chat; conversations CRUD; context budget; usage tracker (measured values only); chat UI with Test connection + model picker.

| Check | Result |
|---|---|
| Backend tests (33: 11 Phase 1 + 10 adapter + 12 chat), Python 3.13 on Colab | PASS |
| Frontend `tsc --noEmit` + `vite build` on Colab | PASS |
| Live call to a real hosted model (Groq) | VERIFIED 2026-10-20 (reported from Colab run; see Live test below) |
| Streaming in a real browser against a running backend | NOT TESTED |
| Docker build | NOT TESTED |
| Ollama / Hugging Face adapters | NOT IMPLEMENTED |

**Fixed:** chat tests failed because `TestClient` skips the lifespan hook; the fixture now calls `init_db`. App startup was unaffected.

**Next:** user creates a free Groq key and sets `OMNI_AI_API_KEY` on the backend (never in chat); run the live test; then Phase 3 (memory).

## Phase 3 — Persistent memory (2026-10-20)

**Built:** `memories` (fact/preference, enable/disable, edit, delete, search) and `notes` tables (migration 2); user-approved only; secrets (API keys, passwords) refused; relevant-only retrieval injected into the model prompt (bounded, master on/off switch); JSON export and all-or-nothing restore (needs `confirm`); Memory tab UI; "Remember" button on chat replies.

| Check | Result |
|---|---|
| Backend tests (43 total, 10 new for memory/notes/export/restore/restart persistence/auth) on Colab | PASS |
| Frontend `tsc --noEmit` + `vite build` on Colab | PASS |
| Memory UI used in a real browser | NOT TESTED |
| Memory effect on a real model's answers | NOT TESTED (needs Groq key) |

**Limits:** retrieval is keyword-based (no embeddings); conversation summarization not built yet.

## Phase 4 — Voice (2026-10-20)
Browser-native speech input/output as a separate module (`frontend/src/voice/`): mic button with recording status, Done/Cancel, editable transcript (never auto-sent), permission/device error messages, read-replies-aloud toggle, voice picker, speed, stop, long replies read in sentence-aligned sections, code blocks skipped.

| Check | Result |
|---|---|
| Pure logic tests (chunking, error messages), vitest, 7 tests on Colab | PASS |
| TypeScript + build | PASS |
| Real microphone / speech synthesis in a browser | NOT TESTED (needs a real browser with mic; support varies; some browsers send audio to the vendor) |
| Wake word | NOT IMPLEMENTED (optional; deferred) |
| Local Whisper | NOT IMPLEMENTED |

## Phase 5 — Tools (2026-10-20)
Tool registry with Pydantic schemas, timeouts, `needs_confirmation` (delete requires `confirm=true`), audit log (tool + outcome only). Tools: calculator (AST whitelist, no eval), date/time, tasks, reminders (shown while the app is open; no background push), notes, authorized document search/read (read-only, `OMNI_DOCS_DIR`, blocks traversal/symlinks/secret-named files/other types). Tools tab UI.

| Check | Result |
|---|---|
| Backend tests: 70 total (27 new for tools) on Colab | PASS |
| Tools UI in a real browser | NOT TESTED |
| Model-driven tool calling from chat | NOT IMPLEMENTED (tools are user-invoked) |
| Health/model-check/export tools | export + provider test exist as endpoints, not registry tools |

## Phase 6 — Web search (2026-10-20)
Adapters: Tavily (free plan 1,000 credits/month, no card — official docs) and self-hosted SearXNG. Brave excluded (no free tier, card + metered billing). Disabled unless configured; in-memory cache; OMNI's own daily cap (`OMNI_SEARCH_DAILY_CAP`, default 30); failed searches aren't counted; chat "Search the web" toggle injects results as UNTRUSTED data and returns clickable sources; failures are shown and chat still answers.

## Phase 7 — Dashboard & polish
Dashboard: quick actions, AI/connection, measured usage (since restart; tokens only if provider-reported), tasks, recent conversations, system (unavailable shown as unavailable). Settings: theme (dark/light/system), model info + test, integrations, backup pointer, security/sign-out, tool activity. Reminder banner while app is open.

## Phase 8 — Hosting files
`docs/DEPLOYMENT.md`, `docker-compose.vm.yml` + `Caddyfile` (HTTPS), `render.yaml` (demo only, ephemeral), `scripts/backup.py`, `.env.example` updated.

| Check (Phases 6–7) | Result |
|---|---|
| Backend tests: 88 total (search adapters, cap, cache, chat integration, status) on Colab | PASS |
| Frontend tsc + vite build + 7 vitest on Colab | PASS |
| Real Tavily/SearXNG call | NOT TESTED |
| Any UI in a real browser | NOT TESTED |
| Docker build, compose, Caddy, any real deployment | NOT TESTED |
| Hosted DB (Supabase/Firebase) backend | NOT IMPLEMENTED |

## End-to-end UI test (2026-10-20, Google Colab)
Real `uvicorn` server + built frontend + headless Chromium (Playwright), scripted fake model/search (no keys, no network): **16/16 PASS** — dashboard connected/usage, chat send + streamed reply + sidebar, web-search source link, test connection, memory add + secret refusal, tools calculator/task/delete-with-confirmation, theme switch, security/audit, backup download, mobile width (no overflow), no uncaught page errors. Run: `backend/e2e/ui_test.py` against `backend/e2e/server.py`.
Still NOT TESTED: real microphone/speech, Docker, real deployment.

## Phase 9 — Agents & coding workspace (2026-10-20)
Sequential manager→role steps on ONE model with checkpoints in SQLite; limits (steps, model calls, seconds/run, one task at a time); quota/outage pauses without losing state and resumes without re-planning; cancel; SSE progress. Roles enabled: manager, research (uses search if configured), planning, coding, review, documentation, data. NOT enabled: testing, devops, skill-creator-as-task, memory (they would need command execution/sandboxing). Coding workspace: read-only viewer; Coding Agent can only create pending diffs; a human approves → file written (stale-file check) → revert possible (refuses to clobber newer edits). Paths confined to `OMNI_WORKSPACE_DIR`; blocks traversal, symlinks, secret-named files, `.git`, non-text types; secrets in proposals rejected. **No command execution exists; "run tests" is not implemented.** No Git branches (not relied on). Parallel agents NOT implemented (sequential by design).

| Check | Result |
|---|---|
| Backend tests: 116 total (agents + workspace + limits/pause/resume/cancel/escape/approval/revert) on Colab | PASS |
| Agents UI in a real browser | NOT TESTED |
| Agents with a real model (plan-JSON reliability varies by model) | NOT TESTED |

## Phase 10 — Skills (2026-10-20)
Declarative skills only (prompt template + input schema + declared permissions + deterministic tests + changelog + provenance). Lifecycle: propose/draft → staged (validated + tests auto-run) → optional AI review (advisory) → human activation with explicit confirm → run → disable/enable/rollback/reject. New skills inactive; failed validation cannot be activated; permission expansion needs extra explicit approval; versions only increase; no endpoint touches security rules/model router/logging; all actions audited. No code-executing skills (no sandbox).

## Phase 11 — Hardening (2026-10-20)
**Verified on Colab: backend 153 passed; frontend tsc OK, build OK, 7 vitest passed; real-browser e2e 19/19 PASS (incl. Agents + Skills UI, under CSP).**
Added: security headers + CSP on pages, `no-store` on API, OMNI's own model-request limiter (`OMNI_MODEL_RPM_LIMIT`, default 20/min; covers chat, agent runs, skill draft/review/run; unauthenticated requests don't consume it). Release checklist: `docs/RELEASE_CHECKLIST.md`. E2E extended to Agents + Skills flows.

## Live model test (2026-10-20, reported from Colab)
Groq key via Colab Secrets (never in chat/repo). `/api/health` 200; `/api/provider/test` ok, 11 models, 421 ms. Streamed replies saved with `done` event: `allam-2-7b` (fallback pick) and `openai/gpt-oss-120b` (selected via PUT /api/provider/model).
Groq catalog for this account now: allam-2-7b, canopylabs/orpheus-*, meta-llama/llama-prompt-guard-2-*, openai/gpt-oss-120b, openai/gpt-oss-20b, openai/gpt-oss-safeguard-20b, qwen/qwen3.8-27b, whisper-large-v3(-turbo). `llama-3.3-70b` is gone; catalog changes often — never hardcode.
Recommended default: `openai/gpt-oss-120b`. Many listed models are not chat models (whisper, orpheus TTS, prompt-guard, safeguard): the model picker should hide/flag them (TODO).
Known gap: Colab e2e needs `pip install playwright && playwright install chromium` on a fresh runtime (add to notebook steps).
Next: plan-JSON reliability test of agents with gpt-oss-120b; filter non-chat models; deployment (Oracle/other); xAI key revocation is the user's.

## Verification update (2026-10-20 evening, reported from Colab @ c558470)
- Backend: 155 passed. Frontend build OK. Browser e2e: 21/21 (Playwright install step added to the notebook).
- Model picker hides non-chat models; default `openai/gpt-oss-120b` confirmed via `/api/provider`. `/api/status` reports the configured default; `connected` stays null until a real test.
- Live agent task on gpt-oss-120b: 5 steps (research, planning, documentation, review, documentation) succeeded with real output. Single run; reliability across many runs untested.
- Demo instance: Colab + cloudflared, production mode, token auth. Ephemeral — data lost on runtime reset; back up regularly.
Remaining: permanent deployment (Oracle, owner must complete card verification), Docker build/compose, voice with a real mic, Ollama/HF adapters, wake word, xAI key revocation (owner).


## Work order 2026-10-20 night (code written, awaiting Colab run)
Added: Ollama + Hugging Face adapters (OpenAI-compatible; non-chat filter applies), `auto` no-signup search (DuckDuckGo scrape -> Wikipedia API; now the default; tests set `search_provider=""`), HF-Dataset persistence sync (`app/services/sync.py`), `OMNI_ALLOW_OPEN_ACCESS`, Settings shows sync + open-access state, `.dockerignore`, compose/Render fixes, docs (DEPLOYMENT, FREE_SERVICES_RESEARCH, VOICE_VERIFICATION).
Expected backend tests after this commit: previous 155 + new (registry 7, search 5, sync 10). **Not yet run.**
Blocked routes (payment walls): HF Docker Spaces (paid plan), Oracle (card), Koyeb (card pre-auth reported).
Docker - cannot be verified without a Docker host: image builds (npm install, vite build, pip install), container start as non-root with `/data` volume ownership, HEALTHCHECK, compose `env_file.required` syntax (needs Compose >= 2.24), Caddy certificate issuance and streaming (`flush_interval -1`) through the proxy, and Render's acceptance of the Docker free plan.
Needs from owner: Render account (check for a card prompt), private HF dataset + fine-grained token, Groq key as a Render env var, an HF token must never be pasted in chat.


## Split architecture + plan ordering (2026-10-20 night)
Direction from the owner: brain Groq, compute Render free, memory Neon Postgres, vault HF private dataset, code GitHub, voice ElevenLabs (browser voice fallback), automation n8n, Cloudflare only if it earns its place. Docs: DEPLOYMENT.md (split map), FREE_SERVICES_RESEARCH.md, POSTGRES_PLAN.md, INTEGRATIONS_PLAN.md. **Built: Groq/Ollama/HF adapters, HF sync. Written-not-verified: Postgres layer. NOT built: ElevenLabs TTS, n8n webhook tool.**
Order: (1) Colab verification of the latest commit; (2) Postgres Option A (awaiting go); (3) ElevenLabs; (4) n8n webhook tool; (5) hosting qualification + deploy + end-to-end test; (6) human voice test.

## Postgres build (Option A) - WRITTEN, NOT VERIFIED
Rules from the owner: `OMNI_DATABASE_URL` flag, SQLite stays default and unchanged; stepwise commits; suite must stay green in SQLite mode; migration = JSON export/restore; every Postgres step below is written-not-verified until Colab runs land (SQLite suite -> local Postgres in Colab -> real Neon).
- Step 1 (db layer) - written, not verified: `PgTarget` stands in for the db path (all ~100 call sites unchanged), pooled psycopg connections (min_size 0, max_idle 240 s, health check, `prepare_threshold=None` for poolers), `translate()` for the few SQLite spellings used (`?`, strftime-now, INSERT OR IGNORE, LIKE->ILIKE, rowid->ctid, lastrowid->RETURNING id), Postgres DDL generated from the SQLite DDL, advisory lock around migrations. Verified only by pure-function tests + a static scan of every SQL string (113 statements) - tests/test_postgres_layer.py (written, not yet run).
- HF snapshot sync is disabled in Postgres mode (it dumps SQLite).
- Known compromise: `rowid` tie-break ordering of conversations becomes `ctid` in Postgres (physical order; only matters when `updated_at` ties).
- Step 2 (call sites) - written, not verified: restore now resyncs Postgres identity counters (`db.resync_sequences`); status/health report the engine and hide local-disk numbers in Postgres mode; two agent tests now go through `db.session` instead of raw sqlite3 so they run on both backends. All 113 SQL strings pass the static translation scan; no call site needed rewriting beyond that (no bool params, no DB-exception control flow).
- Step 3 (Postgres-mode tests) - written, not verified: `TEST_PG_URL=postgresql://... pytest` runs the whole suite on Postgres with one schema per test; SQLite-only tests carry `@pytest.mark.sqlite_only` (test_db, test_sync) and are skipped; `tests/test_postgres_live.py` adds real-server tests (schema, CHECK/CASCADE, RETURNING id, restore-style explicit ids + sequence resync, LIKE/ON CONFLICT/timestamps, unreachable DB). Without TEST_PG_URL nothing changes (SQLite).
- Colab recipe: (a) `pytest -q` with TEST_PG_URL unset = SQLite regression; (b) `apt-get install -y postgresql; service postgresql start; sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'omni'"; export TEST_PG_URL=postgresql://postgres:omni@localhost:5432/postgres; pytest -q` = Postgres mode; (c) later a Neon project with a throwaway database as TEST_PG_URL, then the real app with OMNI_DATABASE_URL.
- Step 2 (translator hardening, a760041) - written, not verified in pytest/Colab: literal/comment-aware, case-insensitive; fixes lowercase `insert into` missing `RETURNING id` and rewrites inside literals/comments. New tests: test_postgres_layer.py (traps), test_postgres_live.py (lowercase insert, OR IGNORE vs NOT NULL/CHECK, literal round-trip), test_edge_cases.py (restore high IDs + sequence resync, ignored insert). Only a standalone dry run of `translate()` was executed.

### Postgres verification (Colab, Mitch, commit 6e8e6ba)
- SQLite regression: 184 passed, 4 skipped, 0 failed. Postgres-mode suite (PostgreSQL 16): 174 passed, 13 skipped, 1 failed (`_PgResult` not iterable) - fixed by making `_PgResult` iterable (sqlite3 parity) + a live test; re-run pending.
- Live smoke in Postgres mode PASSED: health 200, conversation 201, real Groq reply (gpt-oss-120b), memory 201; server killed and restarted on the same `OMNI_DATABASE_URL` - conversation (4 messages) and memory survived. Steps 1-3: VERIFIED in Colab against local Postgres 16 (except the fix above, re-run pending).
- Still unverified: translator hardening + edge tests (a760041), export/restore round-trip on Postgres, real Neon (needs Sebastian's account).

### Postgres sign-off update (Colab, Mitch, e8eff32)
- SQLite suite: 192 passed. Postgres mode (PostgreSQL 16): 186 passed, 0 failures (`_PgResult` fix confirmed). Export/restore round-trip on Postgres PASSED (sentinel conversation + memory present in a fresh DB after restore). Translator hardening and edge tests are included in these runs.
- Remaining for Postgres sign-off: real Neon run (Sebastian creates the account; `OMNI_DATABASE_URL` as a host env var only).
### E2E note
- Isolated `--only agents` / `--only skills` runs in the fresh clone were confounded: `frontend/dist` was not built, so the page returned `{"detail":"Not Found"}` while APIs returned 200. They say nothing about the UI or selectors. Re-run with the frontend built is pending; no UI-duplication theory until then. Lesson: e2e preflight should fail fast if `/` isn't the app.

## UI redesign (holographic OMNI core) - VERIFIED (Colab, HEAD 08aff84)
Commits: 7b8223f (theme tokens) -> 773e952 (OmniCore canvas orb + header) -> 4cf77a9 (dashboard hero + magenta grid, chat empty state, glow accents). Restyle only: no labels/roles/names changed; the orb and hero are `aria-hidden` and contain no text or roles (so `get_by_role("status").first` is still the connection pill). Orb is hand-rolled canvas, ~30 fps cap, paused when tab hidden, static frame under `prefers-reduced-motion`; no new dependencies. Not run: `npm run build`/tsc (npm registry unreachable from my sandbox), vitest, E2E, screenshots. Needs Colab: build + 21/21 E2E + visual comparison to the reference.

### UI redesign verification (Colab, Mitch, fresh clone, HEAD 08aff843352bcf8f5f703d1184a6196097c84851)
- Frontend: `npm install` RC 0; `npm run build` RC 0 (tsc --noEmit && vite build, 42 modules); standalone tsc clean; vitest 7/7.
- Backend (scrubbed env): 192 passed, 8 skipped.
- Playwright E2E: 21/21 passed (incl. agents approve/revert, skills lifecycle, theme switch, mobile no-overflow, no uncaught page errors). This also resolves the earlier two E2E failures: they were environmental (missing `frontend/dist`), not UI bugs; a786887 added the preflight.
- Screenshots vs the reference: accepted by the owner side as the same family (orb with rings in front and behind, magenta grid floor, glass panels, opaque chat); body bg measured #020617; orb in header 34px / dashboard 280px / chat empty state 150px; no console errors. No polish round requested.
- Postgres: verified in Colab on local PostgreSQL 16 (see above); real Neon run still pending.
- Parked: deployment (Render email verification, Neon connection string) awaits Sebastian; Ollama live test in flight.

## ElevenLabs TTS adapter (backend) - WRITTEN, NOT VERIFIED
Server-side only; off unless `OMNI_TTS_PROVIDER=elevenlabs` + `OMNI_TTS_API_KEY` + `OMNI_TTS_VOICE_ID` are set (key is a server env secret, never in repo/browser/logs/errors). With none set, OMNI behaves as before: `GET /api/voice/status` and `/api/status` -> `integrations.tts` report "TTS: not configured. Using browser voices." and `POST /api/voice/speak` returns 503 `not_configured`.
- Endpoints: `GET /api/voice/status`, `POST /api/voice/speak {text}` -> `audio/mpeg` (`X-OMNI-TTS-Cache: hit|miss`). Both behind the normal auth.
- Free-credit guards: per-reply char cap (1500), own monthly char counter (cap 8000, an ESTIMATE, resets on restart, charged only after success), in-memory LRU cache keyed by (voice, model, text) so repeats are free, 2-concurrent semaphore.
- Errors mapped to clear kinds (auth / payment (402, cause deliberately not assumed) / rate_limit / bad_request / timeout / unreachable / provider_error (5xx) / bad_audio / too_long / monthly_cap); no automatic retries; concurrent identical requests share one call; provider response bodies and the key are never echoed.
- Tests: `tests/test_tts.py` (mocked provider via httpx.MockTransport). Not run here (no pytest in my sandbox); the live test waits for Sebastian's key. Unverified: free-plan API access, default model id `eleven_flash_v2_5`, voice ids, the exact error codes ElevenLabs returns (mapping follows common HTTP semantics).
- NOT built: frontend "Voice engine" switch / audio playback (also needs `media-src blob:` in the CSP). Next commit if approved.
