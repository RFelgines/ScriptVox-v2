@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo No .venv found - run setup.ps1 first.
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo frontend\node_modules missing - run setup.ps1 first.
    exit /b 1
)
if not exist ".env" (
    echo No .env found - run setup.ps1 first ^(or copy .env.example to .env yourself^).
    exit /b 1
)

echo Demarrage de ScriptVox...

start "ScriptVox Backend" cmd /k ".venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"

start "ScriptVox Worker" cmd /k ".venv\Scripts\python.exe -m huey.bin.huey_consumer app.workers.tasks.huey -k thread -w 1"

rem Production build by default (fast). "start.bat dev" = Next.js dev server (hot reload, slower).
if /i "%~1"=="dev" (
    start "ScriptVox Frontend" cmd /k "cd frontend && npm run dev"
) else (
    if not exist "frontend\.next\BUILD_ID" (
        echo Building frontend ^(first run^)...
        pushd frontend
        call npm run build
        popd
    )
    start "ScriptVox Frontend" cmd /k "cd frontend && npm run start -- -H 127.0.0.1"
)

timeout /t 6 /nobreak >nul
start http://localhost:3000

echo Tous les services sont lances dans des fenetres separees.
