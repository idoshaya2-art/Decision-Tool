@echo off
cd /d %~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_agent.ps1"
pause
