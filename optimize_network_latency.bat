@echo off
chcp 65001 >nul
:: Batch script tối ưu hóa độ trễ mạng và TCP cho Cast Screen (Yêu cầu Run as Administrator)

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Vui lòng bấm chuột phải vào file này và chọn 'Run as administrator'!
    pause
    exit /b 1
)

echo ========================================================
echo   TỐI ƯU HÓA ĐỘ TRỄ MẠNG (ULTRA-LOW LATENCY TWEAKS)
echo ========================================================
echo.

:: 1. Tắt Network Throttling của Windows Multimedia (Mặc định Windows bóp mạng khi render đồ họa)
echo [+] 1. Tắt giới hạn mạng Multimedia Network Throttling...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v "NetworkThrottlingIndex" /t REG_DWORD /d 4294967295 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile" /v "SystemResponsiveness" /t REG_DWORD /d 0 /f >nul

:: 2. Tối ưu TCP Autotuning & Congestion Provider (BBR / CTCP)
echo [+] 2. Tối ưu TCP TCP/IP Stack...
netsh int tcp set global autotuninglevel=normal >nul
netsh int tcp set global timestamps=disabled >nul
netsh int tcp set global rss=enabled >nul
netsh int tcp set global ecncapability=disabled >nul

:: 3. Tăng độ ưu tiên QoS cho đa phương tiện
echo [+] 3. Cấu hình Gaming / Multimedia Network Priority...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games" /v "GPU Priority" /t REG_DWORD /d 8 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games" /v "Priority" /t REG_DWORD /d 6 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games" /v "Scheduling Category" /t REG_SZ /d "High" /f >nul

echo.
echo ========================================================
echo  [OK] ĐÃ TỐI ƯU HÓA XONG HỆ THỐNG MẠNG VÀ TCP WINDOWS!
echo ========================================================
echo.
pause
