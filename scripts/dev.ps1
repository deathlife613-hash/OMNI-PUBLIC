# Run from the repo root in Windows PowerShell:  .\scripts\dev.ps1
# Starts the backend (port 8000) in this window; open a second window for the frontend:
#   cd frontend; npm install; npm run dev
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path ..\.env)) { Copy-Item ..\.env.example ..\.env; Write-Host "Created .env from template." }
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
