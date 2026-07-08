@echo off
REM Force-keep the cmd window (cmd /k).
REM If flash.bat auto-closes before you can read it, double-click this one instead;
REM the window stays open until you type "exit".
pushd "%~dp0"
cmd /k "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""program.ps1"" -Pause %*"
