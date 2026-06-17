<#
建立「jack-toolkit」launcher 捷徑（內嵌 launcher 圖示）並嘗試釘選到工作列。

設計重點：
  - 捷徑 target = pythonw.exe，引數 = launcher.py，IconLocation = launcher.ico。
  - 刻意不寫顯式 AppUserModelID —— 讓 Windows 用捷徑推導的隱式 AUMID 把執行中
    視窗併回釘選按鈕，點擊釘選捷徑即單一乾淨工作列按鈕。
  - Win10/11 已移除「釘選到工作列」自動化 verb，本腳本盡力嘗試；失敗則建立好捷徑、
    開啟檔案總管並列出手動釘選步驟（Windows 限制，非錯誤）。

用法：
    powershell -ExecutionPolicy Bypass -File pin_launcher_to_taskbar.ps1
#>

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$entry = Join-Path $here 'launcher.py'
$ico   = Join-Path $here 'launcher.ico'

if (-not (Test-Path $entry)) { Write-Host "[ERROR] 找不到 launcher.py: $entry" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $ico))   { Write-Host "[WARN] 找不到 launcher.ico，請先執行: python make_icons.py" -ForegroundColor Yellow }

# 1) 解析 pythonw.exe（無 console 視窗）
$pythonw = $null
try {
    $exe = & python -c "import sys; print(sys.executable)"
    if ($exe) {
        $cand = Join-Path (Split-Path -Parent $exe) 'pythonw.exe'
        if (Test-Path $cand) { $pythonw = $cand }
    }
} catch {}
if (-not $pythonw) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
}
if (-not $pythonw) {
    Write-Host "[ERROR] 找不到 pythonw.exe，請先安裝 Python 3.9+ 並加入 PATH。" -ForegroundColor Red
    exit 1
}
Write-Host "pythonw: $pythonw"

# 2) 建立捷徑（桌面 + 開始功能表）
$wsh = New-Object -ComObject WScript.Shell
function New-Shortcut([string]$path) {
    $sc = $wsh.CreateShortcut($path)
    $sc.TargetPath       = $pythonw
    $sc.Arguments        = '"' + $entry + '"'
    $sc.WorkingDirectory = $here
    if (Test-Path $ico) { $sc.IconLocation = "$ico,0" }
    $sc.Description       = 'jack-toolkit launcher'
    $sc.WindowStyle      = 1
    $sc.Save()
}

$desktop  = [Environment]::GetFolderPath('Desktop')
$startDir = [Environment]::GetFolderPath('Programs')
$lnkDesktop = Join-Path $desktop 'jack-toolkit.lnk'
$lnkStart   = Join-Path $startDir 'jack-toolkit.lnk'
New-Shortcut $lnkDesktop
New-Shortcut $lnkStart
Write-Host "已建立捷徑:" -ForegroundColor Green
Write-Host "  $lnkDesktop"
Write-Host "  $lnkStart"

# 3) 嘗試自動釘選到工作列
$pinned = $false
try {
    $shell  = New-Object -ComObject Shell.Application
    $folder = $shell.Namespace((Split-Path $lnkDesktop))
    $item   = $folder.ParseName((Split-Path $lnkDesktop -Leaf))
    foreach ($v in $item.Verbs()) {
        $n = ($v.Name -replace '&', '')
        if ($n -match '工作列' -or $n -match 'Taskbar') {
            $v.DoIt(); $pinned = $true; break
        }
    }
} catch {}

Write-Host ""
if ($pinned) {
    Write-Host "已嘗試釘選到工作列，請確認工作列是否出現 jack-toolkit 圖示。" -ForegroundColor Green
} else {
    Write-Host "Windows 已停用自動釘選介面，請手動釘選（任一方式）：" -ForegroundColor Yellow
    Write-Host "  方式A：桌面『jack-toolkit』捷徑按右鍵 -> 顯示更多選項 -> 釘選到工作列"
    Write-Host "  方式B：開始功能表搜尋『jack-toolkit』-> 右鍵 -> 釘選到工作列"
    Write-Host "  方式C：先用捷徑開啟 launcher，再對工作列上的圖示按右鍵 -> 釘選到工作列"
    try { Start-Process explorer.exe "/select,`"$lnkDesktop`"" } catch {}
}
