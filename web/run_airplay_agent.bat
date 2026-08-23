@echo off
setlocal
cd /d "%~dp0.."
python web\airplay_agent.py
pause
