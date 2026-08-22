@echo off
:: Auto-request Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Yeu cau quyen Administrator de cau hinh Firewall giu ON...
    powershell -Command "Start-Process '%~0' -Verb RunAs"
    exit /b
)

title Cast Screen Pro - Cho phep Hotspot khi Firewall BAT
echo =======================================================================
echo     Mo quyen Hotspot AirPlay de ban co the BAT Firewall 100%%
echo =======================================================================
echo.

echo [1/4] Cho phep Network Discovery tren profile Public...
netsh advfirewall firewall set rule group="Network Discovery" new enable=Yes >nul 2>&1

echo [2/4] Cho phep tat ca ket noi den tu dai mang Hotspot 192.168.137.0/24...
netsh advfirewall firewall delete rule name="Allow Hotspot Subnet Inbound" >nul 2>&1
netsh advfirewall firewall add rule name="Allow Hotspot Subnet Inbound" dir=in action=allow remoteip=192.168.137.0/24 profile=any enable=yes >nul 2>&1

echo [3/4] Mo toan bo quyen Inbound cho Bonjour mDNSResponder...
netsh advfirewall firewall delete rule name="Bonjour mDNS Public Allow" >nul 2>&1
for /f "tokens=*" %%i in ('where mDNSResponder.exe 2^>nul') do (
    netsh advfirewall firewall add rule name="Bonjour mDNS Public Allow" dir=in action=allow program="%%i" profile=any enable=yes >nul 2>&1
)
if exist "%ProgramFiles%\Bonjour\mDNSResponder.exe" (
    netsh advfirewall firewall add rule name="Bonjour mDNS Public Allow" dir=in action=allow program="%ProgramFiles%\Bonjour\mDNSResponder.exe" profile=any enable=yes >nul 2>&1
)

echo [4/4] Mo toan bo quyen Inbound cho UxPlay Engine...
netsh advfirewall firewall delete rule name="UxPlay Engine Public Allow" >nul 2>&1
netsh advfirewall firewall add rule name="UxPlay Engine Public Allow" dir=in action=allow program="%~dp0engine\bin\uxplay-windows.exe" profile=any enable=yes >nul 2>&1

echo.
echo =======================================================================
echo   [THANH CONG] Da mo toan bo quyen Hotspot! Ban co the BAT Firewall!
echo =======================================================================
echo.
pause
