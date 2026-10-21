# Postgres (Neon) path: scope and honest cost - PLAN ONLY, nothing built yet

## Why
Today: SQLite on the host's disk, plus HF-Dataset snapshot sync for hosts with an ephemeral disk. That loses up to ~2 minutes of writes on a hard kill and needs restore-on-boot logic. Neon free Postgres (1 GB, 100 CU-h/month, no card, permanent per its pricing page) would make every write durable, and lets compute (Render), database (Neon) and model (Groq) be separate free services.

## What the code looks like today (measured)
- ~200 `execute()` call sites in 8 modules (memory 26, skills 22, agents 20+16, chat 13, builtin tools 12, db 10, tools 2), raw SQL with `?` placeholders and `sqlite3.Row`.
- SQLite-specific bits that Postgres rejects or changes: `?` placeholders; `strftime(...)` timestamp defaults and `UPDATE ... updated_at = strftime(...)` (~15 places); `AUTOINCREMENT` (14 tables); `cursor.lastrowid` (~8 places); `INSERT OR IGNORE` (1); `LIKE` is case-insensitive in SQLite but case-sensitive in Postgres (needs `ILIKE`, ~4 places); `PRAGMA` calls; `conn.execute()` shortcut and `sqlite3.Row` access; `sqlite_master` and `iterdump` use in tests and in HF sync.
- Blocking DB calls already run inside async handlers (true for SQLite too).

## Options and cost
| Option | Work | Verdict |
|---|---|---|
| **A. One flag, one dialect layer** - `OMNI_DATABASE_URL=postgresql://...` switches backend; SQLite stays the default | New `db` layer: connection pool (psycopg 3 + pool), `?`->`%s` translation, row factory with dict access, `RETURNING id` shim for `lastrowid`; a second DDL set (Postgres migrations v1-v5); replace the ~30 dialect call sites with portable forms (Python-computed UTC timestamps passed as parameters, `ILIKE` helper, `ON CONFLICT DO NOTHING`). | **Recommended.** About 600-900 changed/added lines. |
| B. Rewrite on SQLAlchemy Core | Touch all ~200 statements; removes dialect bugs for good | More work and regression risk for a personal app; not worth it now |
| C. Dual-write SQLite + Postgres | Two sources of truth, partial-failure states | **Rejected:** consistency problems, no benefit over A |
| D. Keep SQLite + HF sync only | Already built | Remains the fallback; unchanged |

## Effort, honestly
- Build: roughly 3-4 focused commits (db layer; Postgres DDL; call-site cleanup; tests/CI). I can write all of it, but **I cannot run any of it in my sandbox** (no Postgres, no pip). Every step needs a Colab cycle: `apt-get install postgresql` in Colab gives a real server for the full test suite; a Neon free project gives the real-service check.
- Tests: the whole backend suite must run on both backends (a parametrised `make_client`), plus the browser e2e against Postgres. `test_db` schema assertions and HF sync (uses `iterdump`) stay SQLite-only.
- Migration of existing data: **no new tool needed.** The existing JSON export/restore already goes through the db layer, so export from SQLite, point OMNI at Neon, restore.
- Backups on Postgres: JSON export (and Neon's own point-in-time history, whose free-plan retention I have not verified). HF snapshot sync is disabled when `OMNI_DATABASE_URL` is set (it dumps SQLite).

## Runtime costs/risks to accept
- Neon suspends after 5 min idle; the first query after that pays a wake-up delay (documented as not stated - **measure it**). Render also sleeps after 15 min, so the first visit after idle pays both.
- Each query is a network round trip (tens to ~150 ms) instead of a local file read; pooling is required. Chat remains fine; list screens with many queries get slower.
- New dependency (`psycopg[binary]`) in the Docker image.
- Free limits: 100 CU-hours/month (compute stays suspended until next month if exhausted), 1 GB storage (writes blocked past it), 5 GB egress. No deletions per the pricing page; inactivity-deletion policy unverified.
- The database URL contains a password: server-side env var only, never logged or returned by any route (same rule as the model key).
- Two dialects to keep in sync from now on.

## Decision needed
Go/no-go on Option A. If go, I start with the db layer behind the flag (SQLite behaviour unchanged, existing 177+ tests as the safety net), then DDL, then call sites, then dual-backend tests.
