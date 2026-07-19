@echo off
setlocal
cd /d "%~dp0"
title EMBA TAU Simulation - Local Demo

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer and try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local demo environment...
  python -m venv .venv
  if errorlevel 1 goto :failed
)

echo Checking application dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

set APP_ENV=test
set INTOPIA_BACKEND=memory
set APP_REQUIRE_AUTH=false
set OPENAI_AGENT_ENABLED=true
set PYTHONUTF8=1

echo.
echo The demo is starting at http://127.0.0.1:8000/
echo Keep this window open while using the demo.
echo Press Ctrl+C to stop it.
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000/'"
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause
exit /b 0

:failed
echo.
echo The demo could not start. Check the message above.
pause
exit /b 1
