@echo off
title [TERMINAL 1] Cloudflare Live Tunnel (GIU LINK CO DINH)
cd /d "%~dp0"

echo ================================================================
echo   [TERMINAL 1] CLOUDFLARE LIVE TUNNEL - GIU LINK CO DINH
echo ================================================================
echo.
echo Cua so nay se GIU CO DINH DUY NHAT 1 LINK CLOUDFLARE HTTPS.
echo Ban KHONG CAN DONG cua so nay khi sua code hay khoi dong lai server!
echo.
echo ================================================================

"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8080

pause
