@echo off
:: Auto-request Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Yeu cau quyen Administrator de mo Firewall cho Hotspot...
    powershell -Command "Start-Process '%~0' -Verb RunAs"
    exit /b
)

title Cast Screen Pro - Hotspot & Firewall Auto Fixer
echo =======================================================================
echo     Cast Screen Pro - Tu Dong Mo Firewall va Toi Uu Mang Hotspot
echo =======================================================================
echo.

set "ENGINE_DIR=%~dp0engine\bin"
set "ENGINE_EXE=%ENGINE_DIR%\uxplay-windows.exe"
set "BEACON_EXE=%ENGINE_DIR%\uxplay-bluetooth-beacon.exe"

echo [1/6] Xoa cac quyen firewall cu lien quan den Cast Screen...
netsh advfirewall firewall delete rule name="Cast Screen Engine" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen Beacon" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen Python" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen - AirPlay TCP Ports" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen - AirPlay UDP Ports" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen - Hotspot Full Access" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen - iPhone Hotspot Access" >nul 2>&1
netsh advfirewall firewall delete rule name="Cast Screen - Android Hotspot Access" >nul 2>&1

echo [2/6] Mo toan bo quyen mang cho Engine UxPlay va Bluetooth Beacon tren moi Profile (Public/Private/Domain)...
netsh advfirewall firewall add rule name="Cast Screen Engine" dir=in action=allow program="%ENGINE_EXE%" enable=yes profile=any
netsh advfirewall firewall add rule name="Cast Screen Engine" dir=out action=allow program="%ENGINE_EXE%" enable=yes profile=any
if exist "%BEACON_EXE%" (
    netsh advfirewall firewall add rule name="Cast Screen Beacon" dir=in action=allow program="%BEACON_EXE%" enable=yes profile=any
    netsh advfirewall firewall add rule name="Cast Screen Beacon" dir=out action=allow program="%BEACON_EXE%" enable=yes profile=any
)

echo [3/6] Mo quyen mang cho Python mDNS Advertiser...
for /f "tokens=*" %%i in ('where python.exe 2^>nul') do (
    netsh advfirewall firewall add rule name="Cast Screen Python" dir=in action=allow program="%%i" enable=yes profile=any >nul 2>&1
    netsh advfirewall firewall add rule name="Cast Screen Python" dir=out action=allow program="%%i" enable=yes profile=any >nul 2>&1
)

echo [4/6] Mo tat ca cong dich vu AirPlay (TCP 7000, 7001, 7100, 5000-5005 va UDP 5353, 6000, 6001, 7011)...
netsh advfirewall firewall add rule name="Cast Screen - AirPlay TCP Ports" dir=in action=allow protocol=TCP localport=7000,7001,7100,5000-5005 enable=yes profile=any
netsh advfirewall firewall add rule name="Cast Screen - AirPlay UDP Ports" dir=in action=allow protocol=UDP localport=5353,6000,6001,7011 enable=yes profile=any

echo [5/6] Mo quyen cho tat ca cac dai mang Hotspot (Laptop Hotspot, iPhone Hotspot, Android Hotspot)...
netsh advfirewall firewall add rule name="Cast Screen - Hotspot Full Access" dir=in action=allow remoteip=192.168.137.0/24 enable=yes profile=any
netsh advfirewall firewall add rule name="Cast Screen - iPhone Hotspot Access" dir=in action=allow remoteip=172.20.10.0/28 enable=yes profile=any
netsh advfirewall firewall add rule name="Cast Screen - Android Hotspot Access" dir=in action=allow remoteip=192.168.43.0/24 enable=yes profile=any

echo [6/6] Toi uu hoa giao dien mang, do uu tien Metric va che do WeakHost...
powershell -Command "Get-NetConnectionProfile | Where-Object {$_.InterfaceAlias -like '*Local Area Connection*' -or $_.InterfaceAlias -like '*Wi-Fi Direct*' -or $_.InterfaceAlias -like '*Wi-Fi*'} | Set-NetConnectionProfile -NetworkCategory Private -ErrorAction SilentlyContinue" >nul 2>&1
powershell -Command "Set-NetIPInterface -InterfaceAlias '*Local Area Connection*' -InterfaceMetric 5 -WeakHostReceive Enabled -WeakHostSend Enabled -ErrorAction SilentlyContinue; Set-NetIPInterface -InterfaceAlias '*Wi-Fi*' -InterfaceMetric 10 -WeakHostReceive Enabled -WeakHostSend Enabled -ErrorAction SilentlyContinue; Set-NetIPInterface -InterfaceAlias '*vEthernet*' -InterfaceMetric 5000 -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo =======================================================================
echo   [THANH CONG] Da mo Firewall va toi uu toan dien mang Hotspot 100%%!
echo =======================================================================
echo.
pause
