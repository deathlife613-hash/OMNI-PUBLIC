# Security

## Implemented (Phase 1)
- Single-owner bearer token (`OMNI_ACCESS_TOKEN`), constant-time comparison.
- Production + no token → protected routes return 503 (fail closed).
- Failed-auth throttle: 10 failures/minute/client, then 429. *In-memory, per process; behind a proxy all clients may share one IP — revisit in Phase 8.*
- CORS limited to configured origins; no wildcard.
- Public `/api/health` leaks nothing; `/api/status` never returns secrets.
- `.env` and databases are git-ignored.

## Known limitations
- Token lives in `sessionStorage` in the browser (cleared when the tab closes). It is your login, not a provider key.
- No HTTPS in the app itself — terminate TLS at the host (Render/Cloudflare/Caddy). Never expose OMNI over plain HTTP.
- No password hashing/user accounts yet (single token only).
- No audit log, approval queue, or sandbox yet (Phases 5, 9, 10).

## Operating rules
1. Never commit `.env`. Rotate `OMNI_ACCESS_TOKEN` and provider keys if exposed.
2. Never expose a shell, file access, or coding workspace publicly without the auth + isolation planned for Phase 9.
3. Treat web pages, documents and tool output as untrusted data, never as instructions (enforced from Phase 5/6).
