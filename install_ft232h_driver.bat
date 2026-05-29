@echo off
cd /d "%~dp0"

set "PS1=tools\ft232h\tools\install_driver.ps1"

if not exist "%PS1%" goto :missing

echo Launching FT232H driver installer...
echo (will auto-elevate to admin via UAC; click Yes when prompted)
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
exit /b %errorlevel%

:missing
echo [ERROR] %PS1% not found.
echo Make sure you double-clicked this from the jack-toolkit folder root.
pause
exit /b 1
