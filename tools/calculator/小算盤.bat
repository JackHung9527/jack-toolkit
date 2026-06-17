@echo off
rem 小算盤雙擊啟動器：優先 pythonw（無黑色 console），失敗時 main.py 內建
rem 的全域 excepthook 會寫 calculator_error.log 並跳 messagebox 顯示原因。
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
