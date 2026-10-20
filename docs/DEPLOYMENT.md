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
| **C. Render free web service** | **No** (ephemeral, sleeps after ~15 min idle) | No | Demo only. Download a backup before closing the tab. `render.yaml` is for trying it out, not for keeping data |
| Supabase / Firebase | Yes | varies | Needs a new storage layer (not built). Supabase free pauses after ~7 days idle |

See `docs/FREE_SERVICES_RESEARCH.md` for sources and dates. Re-check every plan before relying on it; free tiers change.

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
