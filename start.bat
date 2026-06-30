@echo off
cd /d "%~dp0"

echo Demarrage de ScriptVox...

start "ScriptVox Backend" cmd /k ".venv\Scripts\uvicorn.exe app.main:app --port 8000"

start "ScriptVox Worker" cmd /k ".venv\Scripts\python.exe -m huey.bin.huey_consumer app.workers.tasks.huey -k thread -w 1"

start "ScriptVox Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 6 /nobreak >nul
start http://localhost:3000

echo Tous les services sont lances dans des fenetres separees.
