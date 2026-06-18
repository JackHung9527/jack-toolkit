# 網路優先權 (netpriority)

設定 Windows 網路介面優先權的 tkinter 工具。是 repo 根目錄 `fix_network_priority.bat`（CLI、自我提權）的 GUI 版。

![icon](icon.png)

## 用途

常見情境：一張**沒有網路的乙太網路卡**搶走了預設路由，導致 Wi-Fi 無法上網。把那張卡的優先權調低（提高 metric）即可讓 Wi-Fi 接手。

「優先權」就是 IPv4 的 **interface metric**：**數字越小，優先權越高**。

## 功能

- 列出所有網路介面：介面名稱、硬體描述（Get-NetAdapter）、連線狀態、目前 metric、自動/手動，依 metric 排序（連線中綠字、已斷線灰字）。
- 選一個介面後：
  - **套用優先權**：設成你輸入的 metric（1~9999）。
  - **降到最低 (9000)**：一鍵把該介面降到最低優先權（等同 fix_network_priority.bat）。
  - **改回自動**：恢復 `AutomaticMetric Enabled`。
  - 可勾「同時套用 IPv6」（預設開，與原 bat 行為一致）。
- 讀取免權限；**套用變更會跳 UAC 提權**執行（變更可逆）。
- 設定**重開機後保留**：套用時會把 metric 寫進該介面 GUID 的登錄檔機碼，等同 Windows「網路內容→IPv4→進階→取消自動計量值」。

## 執行

```powershell
python main.py                 # 開發用
python ..\..\launcher.py       # 經 jack-toolkit launcher（本目錄含 manifest.json）
```

## 實作

- 讀取：背景執行緒呼叫 `powershell Get-NetIPInterface / Get-NetAdapter | ConvertTo-Json`，強制 UTF-8 輸出後以 `json` 解析，再 `after(0,...)` 回 UI 執行緒更新表格（避免凍結）。
- 套用：提權腳本先由 ifIndex 解析 `InterfaceGuid`，再做兩件事——
  1. **持久（重開機保留）**：把 `InterfaceMetric` 寫進 `HKLM\SYSTEM\CurrentControlSet\Services\Tcpip(6)\Parameters\Interfaces\{GUID}`（改回自動則刪掉此值）。
  2. **立即生效（不必重開機）**：跑 `Set-NetIPInterface -InterfaceIndex <idx> -InterfaceMetric <n>`（可選 IPv6）。

  透過 `Start-Process powershell -Verb RunAs -Wait -PassThru` 提權執行，並 `exit $p.ExitCode` 把子程序退出碼帶回（否則套用失敗會被誤判成功）；失敗詳情寫 `%TEMP%\netpriority_apply.log` 供顯示。使用者在 UAC 按「是」後套用，完成自動重新整理；取消 UAC 會顯示「已取消」。

> **為何需要寫登錄檔**：單純 `Set-NetIPInterface -InterfaceMetric` 只改 ActiveStore（當前生效），不會落到 PersistentStore，重開機時 Windows 會把 `AutomaticMetric` 重設為 Enabled、依連線速度重算 metric，設定就被沖掉。寫登錄檔（PersistentStore）才會在重開機後保留。

## 還原

把該介面「改回自動」，或在系統管理員 PowerShell 執行：
```powershell
Set-NetIPInterface -InterfaceIndex <idx> -AutomaticMetric Enabled
```
