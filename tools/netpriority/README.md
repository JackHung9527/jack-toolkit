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

## 執行

```powershell
python main.py                 # 開發用
python ..\..\launcher.py       # 經 jack-toolkit launcher（本目錄含 manifest.json）
```

## 實作

- 讀取：背景執行緒呼叫 `powershell Get-NetIPInterface / Get-NetAdapter | ConvertTo-Json`，強制 UTF-8 輸出後以 `json` 解析，再 `after(0,...)` 回 UI 執行緒更新表格（避免凍結）。
- 套用：組 `Set-NetIPInterface -InterfaceIndex <idx> -AddressFamily IPv4 -InterfaceMetric <n>`（可選 IPv6），透過 `Start-Process powershell -Verb RunAs -Wait` 提權執行；使用者在 UAC 按「是」後套用，完成自動重新整理。取消 UAC 會顯示「已取消」。

## 還原

把該介面「改回自動」，或在系統管理員 PowerShell 執行：
```powershell
Set-NetIPInterface -InterfaceIndex <idx> -AutomaticMetric Enabled
```
