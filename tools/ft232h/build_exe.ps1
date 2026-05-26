# 一鍵打包 FT232H Tester 成 single-file exe。
#
# 用法：在 PowerShell 內執行：
#     .\build_exe.ps1
#
# 預期環境：
#   * Python 3.9+ 已安裝
#   * 第一次執行會自動建立 .venv 並安裝 requirements.txt
#   * 產出位置：dist\FT232H_Tester.exe

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$venv = Join-Path $root ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy))
{
    Write-Host "[1/4] Creating virtualenv .venv ..." -ForegroundColor Cyan
    python -m venv $venv
}
else
{
    Write-Host "[1/4] Reusing existing .venv" -ForegroundColor Cyan
}

Write-Host "[2/4] Installing dependencies ..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

Write-Host "[3/4] Cleaning previous build ..." -ForegroundColor Cyan
if (Test-Path "build")
{
    Remove-Item -Recurse -Force "build"
}
if (Test-Path "dist")
{
    Remove-Item -Recurse -Force "dist"
}

Write-Host "[4/4] Running PyInstaller ..." -ForegroundColor Cyan
& $venvPy -m PyInstaller --clean --noconfirm ft232h_tester.spec

if (Test-Path "dist\FT232H_Tester.exe")
{
    Write-Host ""
    Write-Host "Build OK: dist\FT232H_Tester.exe" -ForegroundColor Green
}
else
{
    Write-Host ""
    Write-Host "Build FAILED" -ForegroundColor Red
    exit 1
}
