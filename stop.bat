@echo off
rem Stop Mikke (app and nginx). Add --with-db to stop PostgreSQL too: stop.bat --with-db
cd /d "%~dp0"
".venv\Scripts\python.exe" scripts\serve.py stop %*
