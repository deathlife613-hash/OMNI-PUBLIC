# OMNI — my assistant, my data, my configuration

Personal JARVIS-style assistant: FastAPI backend, React frontend, SQLite storage, a free hosted model as the brain. **Status: Phase 1 (foundation).** No chat yet — see `PROJECT_STATUS.md` for exactly what works and what has been verified.

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

## Docker (untested)
`docker compose up --build` after creating `.env` with `OMNI_ACCESS_TOKEN` set.

## Free-tier honesty
No provider guarantees unlimited free compute, quota, or uptime. Read `docs/FREE_SERVICES_RESEARCH.md` before deploying; SQLite data on hosts with an ephemeral disk is lost on restart.
