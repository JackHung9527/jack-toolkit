# 開發時直接從原始碼啟動（不打包）
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$venv = Join-Path $root ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy))
{
    Write-Host "Creating virtualenv .venv ..." -ForegroundColor Cyan
    python -m venv $venv
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r requirements.txt
}

& $venvPy main.py
