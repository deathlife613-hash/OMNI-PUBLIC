# Deploying OMNI

Last reviewed: 2026-10-20. **Nothing here has been deployed or Docker-built by the authoring assistant — see "Verified vs not" at the end.**

## The one thing to understand first
OMNI keeps your data in a SQLite file. It is only durable if that file sits on a **persistent disk**. On a host with an
ephemeral filesystem (for example Render's free web service) every restart, redeploy or spin-down **erases it**. OMNI
has no hosted-database backend yet, so Supabase/Firebase are *not* drop-in options today.

## Hosting vs. the AI model
Hosting OMNI = where the app and your data live. The AI "brain" is a separate hosted model (Groq etc.) that OMNI's
backend calls with a key you provide. Your browser only talks to OMNI; keys never reach it.

## Options (honest ranking for $0)
| Option | Persistent data? | Card? | Fit |
|---|---|---|---|
| **A. Free always-on VM with a persistent disk** (e.g. Oracle Cloud Always Free — verify current terms; capacity is often unavailable) + `docker-compose.vm.yml` | Yes | Oracle requires one (verify) | Best match for the design |
| **B. Your own computer + a free tunnel** (e.g. Cloudflare Tunnel) | Yes (your disk) | No | Works only while the computer is on; needs software installed there |
| **C. Render free web service** | **Disk is ephemeral**; with OMNI's HF-Dataset sync, data survives restarts (see below) | Unverified | Best no-card candidate; sleeps after ~15 min idle; not production-grade per Render |
| Supabase / Firebase | Yes | varies | Needs a new storage layer (not built). Supabase free pauses after ~7 days idle |

See `docs/FREE_SERVICES_RESEARCH.md` for sources and dates. Re-check every plan before relying on it; free tiers change.

## No-card, always-reachable home: Render free + Hugging Face Dataset sync (recommended for $0)
Checked 2026-10-20 from official docs unless marked. **Not deployed or tested yet.**

| Route | Verdict |
|---|---|
| **Render free web service (Docker) + OMNI's HF-Dataset sync** | Candidate. Free, 750 h/month, spins down after 15 min idle (~1 min cold start), **ephemeral disk** (official). Card requirement is **not stated in Render's docs; community posts are inconclusive - unverified.** If Render asks for a card at signup, stop. Render also calls free services unsuitable for production. Whether the free plan accepts Docker services was not stated on the page I read; secondary sources say yes. |
| Hugging Face **Docker Spaces** | **BLOCKED: HF docs say Docker (and Gradio) Spaces need a paid plan to create.** Free = static Spaces only. Free CPU Space disk is also ephemeral. |
| HF Storage Buckets as a mounted volume | Free to create, but the free allowance wasn't stated and it is only usable from an HF Space (paid for Docker). Not used. |
| Oracle Always Free | **Card required** (official). Stopped on this route. |
| Koyeb | Sources conflict on a card + $29 pre-authorisation. Not recommended. |
| Colab + cloudflared tunnel | Works tonight with no card; runtime resets lose data; a demo, not a home. |

### Persistence design (built, tests written, live run still needed)
- OMNI snapshots its SQLite database as gzipped SQL and pushes it to a **private** HF Dataset repo every `OMNI_SYNC_INTERVAL_S` (default 120 s) **only if the data changed**, and once more on graceful shutdown (SIGTERM).
- On boot, if there is **no local database** (always true after a Render restart), the latest snapshot is restored before the app starts. An existing local database is never overwritten.
- Safety rails: refuses to run if the dataset is **public**; if the startup restore **fails** (HF down), pushes are **blocked** so an empty database cannot overwrite your saved data (restart once HF is back); snapshots over 8 MB are refused with an error; the token never appears in status or logs.
- **What can still be lost:** edits made after the last successful push if the host kills the process without a graceful shutdown (up to ~2 minutes), and anything if you never configure sync. Status → Settings → Integrations shows the last success/error.
- Setup you must do (account steps are yours): (1) huggingface.co → New Dataset → **Private**, e.g. `yourname/omni-data`. (2) Settings → Access Tokens → **fine-grained** token with write access to that one repo only. (3) In Render's dashboard set `OMNI_SYNC_PROVIDER=hf_dataset`, `OMNI_SYNC_HF_REPO`, `OMNI_SYNC_HF_TOKEN`, plus `OMNI_AI_API_KEY`. (4) New Blueprint from `render.yaml`. (5) Open the URL, Chat → Test connection.

## Open access (no login) - the trade-off
By default production **refuses to serve without `OMNI_ACCESS_TOKEN`**. If you want no login, set `OMNI_ALLOW_OPEN_ACCESS=true`. Be clear about what that means on a public URL:
- Anyone who finds or is given the URL can spend **your** model quota (OMNI's own limiter caps model requests at 20/minute, which slows but does not stop abuse), search with your allowance, and **read or replace all your conversations, memories and notes** (restore overwrites everything).
- A hidden URL is not security. Settings shows a red "OPEN ACCESS" notice while this mode is on.
- Safer middle ground if you change your mind: set a short token and keep it in your phone's password manager. A token, when set, is always enforced, even with open access enabled.
- Keep `OMNI_WORKSPACE_DIR` and `OMNI_DOCS_DIR` unset on an open instance.

## Option A: VM steps (you do the account steps; I can't sign in for you)
1. Create the VM (Ubuntu), open ports 80/443, point a DNS A record at it.
2. `sudo apt install -y docker.io docker-compose-v2 git` and clone your repo.
3. `cp .env.example .env`, then set `OMNI_ACCESS_TOKEN` (long random), `OMNI_AI_PROVIDER`, `OMNI_AI_API_KEY`, `OMNI_CORS_ORIGINS` (leave default; same-origin needs no CORS).
4. Edit the domain in `Caddyfile`. Run `docker compose -f docker-compose.vm.yml up -d --build`.
5. Open `https://your-domain`, enter the token, Chat → Test connection → Choose model.
6. Never create a billable resource without checking the plan; set a budget alert if the provider offers one.

## Environment variables
See `.env.example` (every variable documented there). Secrets: `OMNI_ACCESS_TOKEN`, `OMNI_AI_API_KEY`, `OMNI_SEARCH_API_KEY` — server-side only, never committed.

## Backups, restore, migration
- Backup: Memory tab → *Download backup*, or `OMNI_URL=… OMNI_ACCESS_TOKEN=… python scripts/backup.py`.
- Restore / migrate to a new host: deploy the new host, sign in, Memory tab → *Restore backup…* (replaces data there, all-or-nothing).
- Also snapshot the Docker volume `omni-data` if you can.
- Models/providers: change `OMNI_AI_PROVIDER` / key and restart; conversations are unaffected.

## HTTPS, CORS, auth
- Public deployments must use HTTPS (Caddy does this automatically). The access token is sent as a Bearer header, so never use plain HTTP over the internet.
- Production mode refuses private routes if no token is set; 10 wrong tokens/minute/IP are throttled.
- Same-origin deployment (default image) needs no CORS. If you host the frontend separately, build it with `VITE_API_BASE` and add its origin to `OMNI_CORS_ORIGINS`.

## Rotating secrets
Change the value in `.env`, `docker compose up -d`. For a leaked AI key, revoke it in the provider console first.

## When free limits hit
- Model quota/rate limit: OMNI shows the provider's error, keeps your message, and does not switch providers or pay. Retry later or pick another configured free provider.
- Search allowance: OMNI's own daily cap stops searches before the provider's monthly allowance runs out.
- Host sleeps/pauses: data survives only on persistent disks (see above).

## Verified vs not
- Verified: backend and frontend tests/build on Google Colab (see PROJECT_STATUS.md).
- NOT verified: Docker image build, compose files, Caddy, any real deployment, any real provider call.
