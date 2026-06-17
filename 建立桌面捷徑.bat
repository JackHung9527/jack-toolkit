@echo off
rem Create a desktop shortcut for the jack-toolkit launcher (with launcher.ico).
rem Generates a temporary VBScript to build the .lnk; no PowerShell needed.
rem NOTE: keep this file ASCII-only. Chinese text in a non-BOM .bat breaks cmd
rem parsing under the cp950 console (variables silently become empty).
setlocal
cd /d "%~dp0"

rem repo root (strip trailing backslash)
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

rem resolve pythonw.exe (no console window); fall back to python.exe
set "PYW="
for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW for /f "delims=" %%i in ('where python.exe 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
    echo [ERROR] Python not found. Install Python 3.9+ and add it to PATH, then retry.
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\launcher.py" (
    echo [ERROR] launcher.py not found next to this .bat:
    echo         %ROOT%\launcher.py
    echo.
    pause
    exit /b 1
)

rem build a temp VBScript and run it to create the desktop shortcut
set "VBS=%TEMP%\_mk_jtk_lnk.vbs"
> "%VBS%" echo Set sh = CreateObject("WScript.Shell")
>> "%VBS%" echo Set lnk = sh.CreateShortcut(sh.SpecialFolders("Desktop") ^& "\jack-toolkit.lnk")
>> "%VBS%" echo lnk.TargetPath = "%PYW%"
>> "%VBS%" echo lnk.Arguments = """%ROOT%\launcher.py"""
>> "%VBS%" echo lnk.WorkingDirectory = "%ROOT%"
>> "%VBS%" echo lnk.IconLocation = "%ROOT%\launcher.ico,0"
>> "%VBS%" echo lnk.Description = "jack-toolkit launcher"
>> "%VBS%" echo lnk.Save
cscript //nologo "%VBS%"
set "RC=%ERRORLEVEL%"
del "%VBS%" >nul 2>nul

echo.
if "%RC%"=="0" (
    echo OK - Desktop shortcut created: jack-toolkit.lnk
    echo      target : "%PYW%" "%ROOT%\launcher.py"
    echo      icon   : %ROOT%\launcher.ico
) else (
    echo [ERROR] Failed to create shortcut. code=%RC%
)
echo.
pause
