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
- `needs_confirmation = true` on every call (external, consequential). JSON payload, 20 KB cap on OMNI's side (n8n's default max is 16 MB). Timeout configurable, one bounded retry (a sleeping n8n host can take ~1 min to wake). Response is truncated and labelled untrusted. Audit log records target name and outcome, not the payload.

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
