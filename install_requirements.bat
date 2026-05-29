@echo off
cd /d "%~dp0"

where python.exe 1>nul 2>nul
if not "%errorlevel%"=="0" goto :nopython

echo Installing jack-toolkit requirements into this python:
python.exe -c "import sys; print(' ', sys.executable)"
echo.
python.exe -m pip install --upgrade pip
python.exe -m pip install -r requirements.txt
set "_rc=%errorlevel%"

echo.
if "%_rc%"=="0" goto :ok

echo ============================================
echo Install failed with errorlevel %_rc%
echo ============================================
pause
exit /b %_rc%

:ok
echo ============================================
echo Install OK. Re-launch launcher.bat to use it.
echo ============================================
pause
exit /b 0

:nopython
echo [ERROR] python.exe not found in PATH. Install Python 3.9+ first.
pause
exit /b 1
