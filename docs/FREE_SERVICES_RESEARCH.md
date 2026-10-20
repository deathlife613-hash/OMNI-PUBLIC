# Free Services Research

**Date checked:** 2026-10-20 · **Method:** web search only. The authoring sandbox could not fetch official pages directly, so most figures below come from search excerpts. Each row is tagged:

- **[official]** text came from the vendor's own docs/changelog
- **[secondary]** blogs, forums, aggregators — treat as likely, re-verify before relying on it
- **[conflict]** sources disagree
- **[not checked]** not researched in this session

Free tiers change often. **Re-verify the row for any service on its official page before creating an account.**

## 1. AI model providers (the "brain")

| Provider | What's free | Limits | Card? | Notes / risks | Sources |
|---|---|---|---|---|---|
| **GroqCloud** — *recommended primary* | Free plan, no expiry, all models, rate-limited only (no token credits) [secondary] | Per-model RPM/RPD/TPM/TPD at **organization** level; exact numbers shown in console → Limits. One aggregator cites ~30 RPM / 1,000 RPD for a typical model [secondary]. Extra keys/members add no capacity [official community post] | No [secondary + Groq community post] | Free-tier data/privacy guarantees not confirmed — read Groq's terms before sending sensitive data. Exceeding limits → wait or upgrade (we will never auto-upgrade). OpenAI-compatible API. | console.groq.com/docs/rate-limits (not fetched); community.groq.com/t/is-there-a-free-tier-and-what-are-its-limits/790 |
| **Ollama Cloud** — *recommended backup* | Free plan, "light usage" [official pricing mirror] | 1 concurrent cloud model; session limit resets every 5 h, weekly limit every 7 days; no fixed token count [official mirror] | Not stated | Usage is GPU-time based, so heavy models burn quota faster; Ollama occasionally retires cloud models. API: `https://ollama.com/api/chat`, key from ollama.com/settings/keys [secondary] | registry.ollama.ai/cloud; ollama.com/pricing (not fetched) |
| **OpenRouter** `:free` models — *last-resort backup* | Model IDs ending `:free` cost $0/token [official] | **20 req/min; 50 req/day** unless you have *ever* bought ≥$10 credits, then 1,000/day [official]. Negative balance → HTTP 402 even on free models [official]. Failed requests may count toward the daily cap [secondary] | No for free use | Reaching the 1,000/day tier requires a **$10 purchase — a cost, so not assumed**. Free model list rotates. Upstream providers may log prompts. | openrouter.ai/docs/limits |
| **Hugging Face Inference Providers** — *not viable as primary* | $0.10/month credits for free users; PRO $2/month [official] | Free accounts cannot pay-as-you-go; requests return 402 once credits are gone [official/secondary] | No | Credit is far too small for an assistant. Keep adapter optional only. | huggingface.co/docs/inference-providers/pricing |

**Decision (proposed):** primary **Groq**, backup **Ollama Cloud**, optional third **OpenRouter :free**. Model names are deliberately *not* hard-coded; Phase 2 lists each provider's live models and tests tool-calling/JSON/streaming before one is chosen.

## 2. Hosting (backend + frontend)

| Service | Type | Free allowance | Sleep / persistence | Card? | Verdict for OMNI |
|---|---|---|---|---|---|
| **Render** free web service | App host (container) | 512 MB RAM, 0.1 CPU; 750 instance-hours/month per workspace [secondary; Render changelog confirms 15-min spin-down rule] | Spins down after 15 min idle, ~1 min cold start [official changelog + secondary]. **Ephemeral filesystem — SQLite data is lost on restart.** Free Postgres expires after 30 days (+14-day grace) [secondary; an older source said 90 — **[conflict]**, don't use it for data]. No free background workers. | Not required for free [unverified] | **Best realistic $0 app host**, paired with external DB. No 24/7, no continuous agents. |
| **Oracle Cloud** Always Free | Full VM | Ampere A1 ARM; page showed 4 OCPU/24 GB, but a notice reports limits cut to **2 OCPU/12 GB, enforced from 2026-08-18** [secondary quoting Oracle — **[conflict]**]; 2 × tiny AMD micro VMs; 200 GB block storage [official page + secondary] | Persistent disk; idle instances can be reclaimed; "Out of capacity" errors common in popular regions [secondary] | **Yes** — credit/debit card for verification (no prepaid/virtual) [official] | Most capable (always-on, persistent, can host agents/workspace) but needs a card, capacity luck, and limits may have shrunk. **Best upgrade path.** |
| **Koyeb** | App host | One free web service, ~0.1 vCPU, scale-to-zero after 1 h [secondary] | Sleeps; no free workers | **[conflict]**: one source says card + $29 pre-authorization required since Feb 2026; another says no card. Mistral AI acquired Koyeb Feb 2026. | Not recommended until card status is confirmed. |
| **Cloudflare Workers / Pages** | Edge + static | Free: 100,000 req/day, 1,000 req/min burst, 10 ms CPU/invocation, 50 subrequests/request; static asset requests free and unlimited [official]. Python Workers now support ASGI incl. FastAPI [secondary] | No sleep; no continuous workers; D1 free daily row limits enforced since 2026-09-01 [secondary] | No | **Excellent for the static frontend.** Not for a long-running backend. |
| Google Cloud, AWS, Azure, Vercel, Netlify, Hugging Face Spaces, Deno Deploy, GitHub Pages | — | **[not checked]** this session | — | — | To be researched in Phase 8 before choosing a fallback. |

## 3. Databases

| Service | Free allowance | Catch | Verdict |
|---|---|---|---|
| **Supabase** Free Postgres | 2 projects, 500 MB DB, 1 GB files, 5 GB egress, 50k MAU, unlimited API requests [secondary] | **Project pauses after 7 days of inactivity**; manual restore required [secondary]. Regular use keeps it awake. | Best fit for durable storage when the app host has an ephemeral disk. Needs a Postgres storage adapter (Phase 8). |
| **SQLite** (file) | Free, built in | Only durable on a persistent disk (Oracle VM, local, Docker volume) | Default for local/dev and Oracle. |
| Firebase Spark | **[not checked]** | — | Evaluate in Phase 8. |

## 4. Proposed $0 deployment

**Phases 1–7: run on your own computer** (backend + browser). No hosting needed, no accounts, no cost.

**Online (Phase 8), Plan A:** one Render free web service serving backend + built frontend, Supabase free Postgres for data, Groq as brain.
- *Compromises:* ~1 min cold start after 15 min idle; reminders/background jobs only run while awake; agent tasks must run inside a request or be resumed on wake; coding workspace stays local/read-only; Supabase needs periodic activity.

**Plan B (upgrade path):** Oracle Always Free VM + Docker Compose + SQLite on its disk. Requires a card for verification (no charge unless you upgrade) and available capacity.

**If a free tier changes:** frontend → Cloudflare Pages (no migration pain); backend → any container host via the Dockerfile; data → `export` (Phase 3) then restore; brain → switch `OMNI_AI_PROVIDER`.

## 5. Cost guardrails
OMNI never enables billing, buys credits, or routes to a paid provider on its own (`OMNI_ALLOW_PAID_PROVIDERS=false`). You must create accounts and decline any paid-upgrade prompts yourself.


## Web search providers (checked 2026-10-20)
| Service | Free? | Card | Verdict | Source |
|---|---|---|---|---|
| Tavily | Yes — "1,000 free API Credits every month" | "No credit card required" | **Used** (adapter `tavily`). Rate limits/commercial terms not stated on that page: verify before heavy use | https://docs.tavily.com/guides/api-credits |
| Brave Search API | No free tier since Feb 2026; $5 monthly credit only with public attribution | Card required, billed after credit, no spending cap | **Excluded** (violates no-card/no-surprise-billing rule); per secondary report https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing.md | secondary source |
| SearXNG | Free software; you host it | n/a | Adapter `searxng` (needs your own instance with JSON enabled) | https://docs.searxng.org |
