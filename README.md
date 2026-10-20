# OMNI — my assistant, my data, my configuration

Personal JARVIS-style assistant: FastAPI backend, React frontend, SQLite storage, a free hosted model as the brain. **Status: Phases 1–8 built.** Chat with a free hosted model, memory & notes, voice, tools, optional web search, dashboard/settings, deployment files. Automated tests pass; live model calls, real-browser use and Docker are NOT yet verified — see `PROJECT_STATUS.md` for the exact PASS / FAIL / NOT TESTED list.

## Install once
- Python 3.11+ ([python.org](https://www.python.org/downloads/), tick "Add to PATH")
- Node.js 20+ ([nodejs.org](https://nodejs.org))
- Git (optional)

## Run locally (Windows PowerShell)
Run from the `omni` folder.

**Window 1 – backend**
```powershell
.\scripts\dev.ps1
```
You should see `Uvicorn running on http://127.0.0.1:8000`. Check `http://127.0.0.1:8000/api/health` → `{"status":"ok",...}`.

**Window 2 – frontend**
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`. The dashboard should show "Backend connected".

Linux/macOS: use `./scripts/dev.sh` instead of the PowerShell script.

## Run the tests
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

## Configuration
Copy `.env.example` to `.env` (the dev script does this). Key settings: `OMNI_ACCESS_TOKEN`, `OMNI_AI_PROVIDER`, `OMNI_AI_API_KEY`. Keys stay on the backend.

## First chat
1. Create a free Groq account/key (console.groq.com), put it in `.env` as `OMNI_AI_API_KEY` (never paste keys into chat or commit them).
2. Restart the backend, open the app → **Chat** → *Test connection* → *Choose model*, then send a message.
3. Optional: `OMNI_SEARCH_PROVIDER=tavily` + `OMNI_SEARCH_API_KEY` for web search; `OMNI_DOCS_DIR` for read-only document search.

## Deploying
Read `docs/DEPLOYMENT.md` first (persistence matters). Docker files are untested.

## Free-tier honesty
No provider guarantees unlimited free compute, quota, or uptime. Read `docs/FREE_SERVICES_RESEARCH.md` before deploying; SQLite data on hosts with an ephemeral disk is lost on restart.
