@echo off
rem Calibration designer launcher: prefer pythonw (no console window).
rem If startup fails, main.py's global excepthook writes calib_designer_error.log
rem and pops a messagebox with the reason (e.g. missing matplotlib).
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
