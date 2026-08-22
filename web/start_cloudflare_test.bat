@echo off
title Cast Screen Pro - Cloudflare Live Tunnel
cd /d "%~dp0"

echo =========================================================
echo   CAST SCREEN PRO - CLOUDFLARE LIVE HTTPS TUNNEL
echo =========================================================
echo.

:: 1. Don dep tien trinh cu neu co
taskkill /f /im cloudflared.exe >nul 2>&1

:: 2. Khoi dong Web Server tren may cua ban
echo [1/2] Dang khoi dong Web Server tren may ban (Port 8080)...
start "CastScreen_WebServer" /min python local_server.py 8080

timeout /t 2 >nul

:: 3. Chay Cloudflare Tunnel truc tiep
echo [2/2] Dang tao duong link HTTPS tu Cloudflare Edge...
echo.
echo =========================================================
echo   HAY COPY DUONG LINK https://xxxx.trycloudflare.com
echo   HIEN THI O BEN DUOI VA MO TREN MAY TINH / DIEN THOAI:
echo =========================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://localhost:8080

echo.
echo Da dung Cloudflare Tunnel.
pause
