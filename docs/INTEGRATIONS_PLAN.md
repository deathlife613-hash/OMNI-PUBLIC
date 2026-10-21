# ElevenLabs voice and n8n automation: scope and contracts (PLAN ONLY, nothing built)

Facts below were fetched 2026-10-20 (some via a summarizer or secondary articles; marked). Re-verify before relying on them.

## 1. ElevenLabs as OMNI's voice layer
**Free plan (pricing page + secondary article):** $0, 10k credits/month, about 10 minutes of TTS, 2 concurrent requests, 128 kbps MP3. API access is **not stated on the pricing page**; a secondary article (developer.puter.com, Jun 2026) says the free plan includes API access to most endpoints. **No commercial license on free** (personal use only). Card requirement not stated. TTS cost: ~1 credit/character on Multilingual, ~0.5 on Flash models (secondary). Output formats above 128 kbps MP3 need paid tiers. **Do not treat as verified until the first real call with a free key succeeds.**

**API (official docs):** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`, header `xi-api-key`, JSON body `text` + optional `model_id`, query `output_format` (default `mp3_44100_128`). A streaming variant and WebSockets exist. Max characters per request: not stated on the page I read.

**Design (Option "adapter + fallback"):**
- Server adapter `TTSProvider` (ElevenLabs first), `POST /api/voice/speak {text}` returns `audio/mpeg`. Key lives only in server env: `OMNI_TTS_PROVIDER=elevenlabs`, `OMNI_TTS_API_KEY`, `OMNI_TTS_VOICE_ID`, `OMNI_TTS_MODEL` (verify names with `GET /v1/models`). The key is never sent to the browser, logged, or put in chat/repo.
- **Free-credit protection:** per-reply character cap, an own monthly character counter (`OMNI_TTS_MONTHLY_CHAR_CAP`, default well below 10k, shown as an *estimate*; ElevenLabs' real balance endpoint is to be verified), and an in-memory cache keyed by (voice, model, text) so replays cost nothing. Off by default per reply unless the user enables "Speak with ElevenLabs".
- **Fallback:** no key, 401/402/429, timeout or quota cap -> the frontend silently falls back to the existing browser voice and shows why. Text is always visible.
- Frontend: Voice bar gets "Voice engine: Browser / ElevenLabs"; audio fetched with the normal auth header, played via an `Audio` element, with the same Stop control.
- Privacy: the reply text is sent to ElevenLabs. Document next to the Groq data note.
- Open-access mode: anyone with the URL could burn the credits; the caps bound the damage.
- Cost to build: ~300 lines, 1-2 commits, ~8 mocked-HTTP tests. Live test needs an account + key (owner enters it as a Render env var / Colab secret himself). That live test becomes the real target of the voice verification item; the 7 browser-voice steps in `docs/VOICE_VERIFICATION.md` stay as is.

## 2. n8n as OMNI's automation layer
**OMNI -> n8n (outbound): a `webhook_post` tool.**
- Named targets only: `OMNI_N8N_WEBHOOKS` (name -> URL). The URL carries the secret path, so it is env-only and never returned by any API or shown in the UI; the model/UI only ever sees the name.
- Optional header auth to match n8n's Webhook node "Header auth" (`OMNI_N8N_AUTH_HEADER`, `OMNI_N8N_AUTH_VALUE`); n8n also supports Basic and JWT auth and an IP allowlist (official docs).
- `needs_confirmation = true` on every call (external, consequential). JSON payload, 20 KB cap on OMNI's side (n8n's default max is 16 MB). Timeout configurable (`OMNI_N8N_TIMEOUT_S`, default 20 s). **No automatic retry** (revised by the owner's rule: a retry can repeat the workflow's side effects; one invocation = one POST. A sleeping host may need the user to simply run it again). Response is truncated and labelled untrusted. Audit log records target name and outcome, not the payload.

**n8n -> OMNI (inbound): workflows call OMNI's existing `/api/*`.**
| Mode | How n8n authenticates | Caveat |
|---|---|---|
| Token mode (recommended) | HTTP Request node with `Authorization: Bearer <OMNI token>` stored as an n8n credential | The single owner token is full access. Planned: a second, narrower `OMNI_AUTOMATION_TOKEN` limited to notes/tasks/memory/tool-run (not restore/export/settings) |
| Open-access mode | No header needed | Anyone can make the same calls. If n8n is used at all, prefer token mode |
Anything n8n sends into OMNI is untrusted data and must never override OMNI's rules (same prompt-injection stance as search results).

**What n8n needs from its host (for the no-card qualification test; no host chosen):**
| Need | Detail |
|---|---|
| Image / runtime | Docker image `n8nio/n8n` (Node app) |
| Port | 5678 (`N8N_PORT`) |
| Persistent storage | `/home/node/.n8n` holds its SQLite DB **and encryption key**; lose it and saved credentials are unrecoverable. Alternative: n8n on Postgres via env (a *separate* Neon free project would avoid needing a disk - to be verified) |
| Env vars | `N8N_ENCRYPTION_KEY` (set explicitly so it survives restarts), `WEBHOOK_URL` (public https URL, required behind a proxy so production webhook URLs are right), `N8N_HOST`/`N8N_PROTOCOL`, optionally `N8N_PAYLOAD_SIZE_MAX`. (n8n's env-var reference page returned 404 for me; these come from n8n docs summaries - verify.) |
| Always-on? | Webhooks and scheduled triggers do not fire while the host sleeps (e.g. Render free spins down after 15 min). OMNI-initiated calls wake it; schedules are unreliable on sleeping hosts |
| RAM | Minimum not stated on the pages I read; a 512 MB free slot may be tight - unverified |
| License | n8n Sustainable Use License (GitHub LICENSE.md): own internal / non-commercial / personal use is allowed; selling it or providing it to others for a fee is not |
| Egress | Outbound HTTPS to OMNI's URL (and whatever workflows call) |

Cost to build the OMNI side: ~250 lines, 1-2 commits, ~10 mocked tests; the optional narrow token adds ~100 lines. The n8n side cannot be tested until a host passes qualification.

## 3. Plan ordering (updated)
1. **P0:** Colab verification of the latest commit (Mitch).
2. **Postgres Option A** (`docs/POSTGRES_PLAN.md`) - awaiting explicit go.
3. **ElevenLabs TTS** adapter + fallback.
4. **n8n webhook tool** (+ optional automation token).
5. **Hosting qualification** (Render, then n8n slot), deploy, real end-to-end test.
6. **Human voice test** (browser steps, then ElevenLabs).


### n8n outbound tool - BUILT (mocked-tested; second-opinion hardening folded in)
Env: `OMNI_N8N_WEBHOOKS` (JSON `{"name":"https://..."}`), optional `OMNI_N8N_AUTH_HEADER` + `OMNI_N8N_AUTH_VALUE`, `OMNI_N8N_TIMEOUT_S` (20), `OMNI_N8N_MAX_PAYLOAD_BYTES` (65536), `OMNI_N8N_MAX_JSON_DEPTH` (8), `OMNI_N8N_RESPONSE_MAX_CHARS` (500, preview only), `OMNI_N8N_ALLOW_PRIVATE` (default false). Tool `webhook_post {target, payload}`, `needs_confirmation`.
- **SSRF guard (default deny):** loopback, private, link-local (incl. cloud metadata 169.254.x), multicast, reserved and unspecified destinations are refused, including hostnames that RESOLVE to them (checked right before each send; every returned address must pass). The destination only ever comes from server env, never from a tool argument. Redirects are never followed. **Explicit exception:** `OMNI_N8N_ALLOW_PRIVATE=true` for a deliberately private self-hosted n8n (same box or LAN). Plain `http` is accepted only to loopback with that flag (same-machine traffic); LAN targets must be `https`. Residual risk: DNS can change between the lookup and the connection (rebinding); the flag is the real control, so leave it off unless n8n is private on purpose.
- **Validation:** at startup and again before sending: https required (except loopback-http above), no embedded credentials, no fragments, no non-http(s) schemes, ports limited to default/443/5678/8443.
- **Idempotency:** every call gets a unique `operation_id` (sent in the body as `{"omni":{"operation_id","sent_at"},"payload":{...}}` and as header `X-OMNI-Operation-Id`). A timeout or mid-response failure is reported as **OUTCOME UNKNOWN** (never auto-resent, never "failed cleanly"); only a failure to connect is reported as not delivered. **Workflows should de-duplicate on `operation_id`.**
- **Limits:** 64 KiB request body, JSON depth 8, 5 s connect + 20 s total timeout, response bytes read are capped, the agent only gets a short `preview` labelled untrusted (never the raw body or exception text).
- **Secrecy:** logs and results carry only the target NAME + operation id. httpx's own request logging is set to WARNING because it would print the full URL. Status shows names, counts and booleans only. The audit log records the tool name + outcome only (no target column).
- **Callbacks (inbound):** n8n calls OMNI's normal authenticated `/api/*` (Bearer token). No open internal endpoint was added and none should be. Replay protection is the operation id + `sent_at` timestamp (the workflow should reject duplicates and stale ones). With a token set it is the full-access owner token (no narrower automation token yet). Under open-access (`OMNI_ALLOW_OPEN_ACCESS=true`) anyone with OMNI's URL can make the same calls; no second auth scheme was invented. Prefer token mode if n8n is used at all.
### Live-test gate (only when an n8n host exists; Sebastian does the signup)
1. **Config/secrecy:** set `OMNI_N8N_WEBHOOKS` as a host env var; `GET /api/status` shows the target name and counts only; grep logs/responses for the URL path: no hits.
2. **One outbound:** `webhook_post` with confirm to a test workflow that just records what it receives; check the envelope, `operation_id` header and body.
3. **Callback:** the workflow calls OMNI (`POST /api/tools/note_add/run`) with `Authorization: Bearer <token>`; the note appears.
4. **End to end:** outbound -> workflow -> callback -> visible result, once.
5. **Negative auth:** wrong/missing webhook auth gives a 401/403 notice; wrong OMNI token on the callback gives 401.
6. **Open-access vs token:** repeat the callback with and without a token in both modes and record exactly what is reachable.
7. **Failure and duplication:** stop the workflow (expect 404/unreachable notice), make it slow (expect OUTCOME UNKNOWN, no resend), send the same operation id twice and confirm the workflow de-duplicates.
