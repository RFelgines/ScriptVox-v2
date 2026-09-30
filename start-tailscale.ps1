# Launch the 3 ScriptVox processes (API, Huey worker, frontend) in parallel
# and stop all of them together on Ctrl-C. Mirrors start.sh — keep both in sync.
#
# Usage:  .\start.ps1          production frontend (fast; rebuilt automatically when sources changed)
#         .\start.ps1 -Dev     Next.js dev server (hot reload; slower)
param([switch]$Dev)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv-rocm\Scripts\uvicorn.exe")) {
    Write-Error "No .venv-rocm found - voir README / installation ROCm."
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
    Write-Host "==> Starting API (uvicorn) on 0.0.0.0:8000 (local + Tailscale)"
    $procs += Start-Process -FilePath ".venv-rocm\Scripts\uvicorn.exe" `
        -ArgumentList "app.main:app", "--host", "0.0.0.0", "--port", "8000" -NoNewWindow -PassThru

    Write-Host "==> Starting Huey worker"
    $procs += Start-Process -FilePath ".venv-rocm\Scripts\python.exe" `
        -ArgumentList "-m", "huey.bin.huey_consumer", "app.workers.tasks.huey", "-k", "thread", "-w", "1" `
        -NoNewWindow -PassThru

    if ($Dev) {
        Write-Host "==> Starting frontend (Next.js, dev mode) on :3000"
        $procs += Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" `
            -WorkingDirectory "frontend" -NoNewWindow -PassThru
    } else {
        # Production build (audit 2026-09-25, UX-10): the dev server compiles every page on
        # first visit. Rebuild only when the sources are newer than the last build.
        $buildId = "frontend\.next\BUILD_ID"
        $needBuild = -not (Test-Path $buildId)
        if (-not $needBuild) {
            $built = (Get-Item $buildId).LastWriteTime
            $newest = Get-ChildItem "frontend\src", "frontend\package.json" -Recurse -File |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
            $needBuild = $newest.LastWriteTime -gt $built
        }
        if ($needBuild) {
            Write-Host "==> Building frontend (first run or sources changed)"
            Push-Location frontend
            try {
                npm run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }
            } finally { Pop-Location }
        }
        Write-Host "==> Starting frontend (Next.js, production) on 0.0.0.0:3000 (local + Tailscale)"
        $procs += Start-Process -FilePath "npm.cmd" -ArgumentList "run", "start", "--", "-H", "0.0.0.0" `
            -WorkingDirectory "frontend" -NoNewWindow -PassThru
    }

    Write-Host ""
    Write-Host "API:      http://localhost:8000 ou http://100.105.224.16:8000  (docs at /docs)"
    Write-Host "Frontend: http://localhost:3000 ou http://100.105.224.16:3000"
    Write-Host "Press Ctrl-C to stop all three."

    Wait-Process -Id ($procs | ForEach-Object { $_.Id })
}
finally {
    Stop-All
}
