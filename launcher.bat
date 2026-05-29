@echo off
cd /d "%~dp0"

where pythonw.exe 1>nul 2>nul
if "%errorlevel%"=="0" goto :go_silent

where python.exe 1>nul 2>nul
if "%errorlevel%"=="0" goto :go_console

echo [ERROR] Neither pythonw.exe nor python.exe found in PATH.
echo Install Python 3.9+ first.
pause
exit /b 1

:go_silent
start "" pythonw.exe launcher.py
exit /b 0

:go_console
start "" python.exe launcher.py
exit /b 0
