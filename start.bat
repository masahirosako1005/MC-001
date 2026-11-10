@echo off
rem Start Mikke: PostgreSQL -> migrations -> nginx (https://localhost:8000) + app (127.0.0.1:8080).
rem Stop with Ctrl+C or stop.bat.   Usage: start.bat [--no-migrate]
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [mikke] .venv not found. Do the setup steps in README.md first.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\serve.py start %*
