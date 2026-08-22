@echo off
title Cast Screen Pro - iOS to PC Mirroring
cd /d "%~dp0"

echo ========================================================
echo        Cast Screen Pro - iOS to Windows Mirroring
echo ========================================================
echo.

:: Check python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python. Vui long cai dat Python 3.10+ va chon 'Add Python to PATH'.
    pause
    exit /b 1
)

:: Launch App
echo Dang khoi dong ung dung...
start pythonw app.py

exit /b 0
