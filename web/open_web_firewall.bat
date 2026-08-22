@echo off
:: Batch script to open Windows Firewall for Cast Screen Web (Port 8080 & 8443)
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Đang yêu cầu quyền Administrator...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    pushd "%CD%"
    CD /D "%~dp0"

echo =========================================================
echo   MO CONG TUONG LUA WINDOWS FIREWALL CHO CAST SCREEN WEB
echo =========================================================

netsh advfirewall firewall add rule name="CastScreen-Web-8080" dir=in action=allow protocol=TCP localport=8080
netsh advfirewall firewall add rule name="CastScreen-Web-8443" dir=in action=allow protocol=TCP localport=8443

echo.
echo [THANH CONG] Da mo cong 8080 va 8443 cho phep dien thoai ket noi!
echo.
pause
