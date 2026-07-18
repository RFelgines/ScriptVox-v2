# One-time (and safe-to-rerun) setup: Python venv + backend deps + frontend deps
# + scaffold the two .env files from their templates (never overwritten if present).
# Mirrors setup.sh — keep both in sync.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

Write-Host "==> Backend: Python virtual environment"
if (-not (Test-Path ".venv")) {
    & $PythonBin -m venv .venv
    Write-Host "    created .venv"
} else {
    Write-Host "    .venv already exists, reusing it"
}

Write-Host "==> Backend: installing dependencies (requirements.txt)"
& .venv\Scripts\pip.exe install --upgrade pip -q
& .venv\Scripts\pip.exe install -r requirements.txt -q
Write-Host "    done (requirements-qwen.txt is NOT installed - GPU-only, opt-in, see README)"

Write-Host "==> Backend: environment file"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "    created .env from .env.example - edit it to choose your LLM provider"
} else {
    Write-Host "    .env already exists, left untouched"
}

Write-Host "==> Frontend: npm dependencies"
Push-Location frontend
try {
    npm install --no-fund --no-audit
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "==> Frontend: environment file"
if (-not (Test-Path "frontend\.env.local")) {
    Copy-Item "frontend\.env.example" "frontend\.env.local"
    Write-Host "    created frontend\.env.local from frontend\.env.example"
} else {
    Write-Host "    frontend\.env.local already exists, left untouched"
}

if (Test-Path "scripts\doctor.py") {
    Write-Host ""
    & .venv\Scripts\python.exe scripts\doctor.py
}

Write-Host ""
Write-Host "Setup complete. Next: .\start.ps1"
