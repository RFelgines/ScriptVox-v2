# Launch the 3 ScriptVox processes (API, Huey worker, frontend) in parallel
# and stop all of them together on Ctrl-C. Mirrors start.sh — keep both in sync.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\uvicorn.exe")) {
    Write-Error "No .venv found - run .\setup.ps1 first."
    exit 1
}
if (-not (Test-Path "frontend\node_modules")) {
    Write-Error "frontend\node_modules missing - run .\setup.ps1 first."
    exit 1
}
if (-not (Test-Path ".env")) {
    Write-Error "No .env found - run .\setup.ps1 first (or copy .env.example yourself)."
    exit 1
}

$procs = @()

function Stop-All {
    Write-Host ""
    Write-Host "Stopping..."
    foreach ($p in $procs) {
        # /T kills the whole process tree. npm.cmd spawns node.exe (next dev) as a
        # child, and a plain Stop-Process only kills npm.cmd itself, leaving the
        # actual dev server running — the same orphan-process trap start.sh hit.
        taskkill /PID $p.Id /T /F 2>$null | Out-Null
    }
}

try {
    Write-Host "==> Starting API (uvicorn) on :8000"
    $procs += Start-Process -FilePath ".venv\Scripts\uvicorn.exe" `
        -ArgumentList "app.main:app", "--port", "8000" -NoNewWindow -PassThru

    Write-Host "==> Starting Huey worker"
    $procs += Start-Process -FilePath ".venv\Scripts\python.exe" `
        -ArgumentList "-m", "huey.bin.huey_consumer", "app.workers.tasks.huey", "-k", "thread", "-w", "1" `
        -NoNewWindow -PassThru

    Write-Host "==> Starting frontend (Next.js) on :3000"
    $procs += Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" `
        -WorkingDirectory "frontend" -NoNewWindow -PassThru

    Write-Host ""
    Write-Host "API:      http://localhost:8000  (docs at /docs)"
    Write-Host "Frontend: http://localhost:3000"
    Write-Host "Press Ctrl-C to stop all three."

    Wait-Process -Id ($procs | ForEach-Object { $_.Id })
}
finally {
    Stop-All
}
