@echo off
rem Circuit calculator launcher: prefer pythonw (no console window). If startup
rem fails, main.py's global excepthook writes circuit_calc_error.log and pops a
rem messagebox with the reason.
cd /d "%~dp0"

where pythonw.exe 1>nul 2>nul
if "%errorlevel%"=="0" (
    start "" pythonw.exe main.py
    exit /b 0
)

where python.exe 1>nul 2>nul
if "%errorlevel%"=="0" (
    start "" python.exe main.py
    exit /b 0
)

echo [ERROR] Neither pythonw.exe nor python.exe found in PATH.
echo Install Python 3.9+ first, then double-click again.
pause
exit /b 1
