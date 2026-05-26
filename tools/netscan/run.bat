@echo off
setlocal
cd /d "%~dp0"

rem Prefer pythonw.exe so GUI launches without a console window.
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw network_scanner.py
    goto :eof
)

where py >nul 2>&1
if not errorlevel 1 (
    start "" py -3w network_scanner.py
    goto :eof
)

rem Fall back to python.exe; use start so this cmd window can close
rem immediately. If GUI fails to start you won't see the error, so run
rem `python network_scanner.py` manually to debug.
where python >nul 2>&1
if not errorlevel 1 (
    start "" python network_scanner.py
    goto :eof
)

echo [ERR] Python not found in PATH.
echo Install Python 3 from https://www.python.org/downloads/
pause
exit /b 1
