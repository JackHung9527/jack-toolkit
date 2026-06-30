# USB-HID 測試工具

host 端的 USB-HID 終端機，用來測試自製 HID 裝置（例如 STM32 custom HID）。介面風格刻意比照
[串列埠工具](../serial/)：左側是收發 log（ASCII / HEX / 對照 三分頁），右側是控制面板。

## 功能

- **列舉 HID 裝置**：列出系統上所有 HID collection，顯示 `VID:PID`、product string、
  usage page / usage、序號、interface。一個實體裝置在 Windows 上可能拆成多個 collection
  （不同 usage page），各列一筆；自製裝置請挑你的 vendor-defined 那一筆。
- **開啟指定 collection**：一律用 `open_path()` 開啟選定的那一筆（不是用 VID/PID 開，
  避免多 collection 時開錯）。
- **Input report**：背景執行緒以 non-blocking 輪詢，收到就即時顯示（標記 `IN`）。
- **Output report**：HEX 或 ASCII payload，標記 `OUT`。支援單筆 / 連續傳送（間隔可調）。
- **Feature report**：Get（標記 `FGET`）/ Set（標記 `FSET`）。
- **Report ID 與補零**：Report ID 為獨立欄位（裝置沒用 numbered report 就填 `00`）；
  可勾「補零至 N bytes」把報告補滿固定長度（Windows 對 Output / Feature 常要求送滿
  report 長度時很有用）。
- 收發各方向以不同顏色標示，跳脫字元（CR/LF/不可列印）在 ASCII 視圖以淺藍標出。

## Report ID 與 payload 的關係

HID 的 Output / Feature report 第一個 byte 是 **Report ID**。本工具把它獨立成欄位，
實際送出的 bytes = `[Report ID] + payload`：

- 裝置**沒有**使用 numbered report → Report ID 填 `00`（它不會被當成資料，但仍需佔位）。
- 裝置**有**使用 numbered report → 填對應的 ID。

收到的 Input report 同理：若裝置使用 numbered report，顯示資料的第一個 byte 即為 Report ID。

## 依賴

```powershell
pip install hidapi
```

Windows 的 `hidapi` wheel 自帶 `hidapi.dll`，走 OS 內建 HID driver，**不需要** Zadig 換 driver，
也不會碰到 ft232h 那種 libusb backend 的麻煩。

## 執行

```powershell
python tools/usbhid/main.py
```

或雙擊 [usbhid.bat](usbhid.bat)（優先用 `pythonw.exe`，沒有黑色 console window）。
也可經 launcher 啟動。

## 已知限制與疑難排解

- 系統 HID（鍵盤 / 滑鼠）通常被 OS 獨佔，`open_path()` 可能失敗或收不到資料 —— 這是
  Windows 的保護機制，非工具問題。本工具的主場景是 vendor-defined 的自製裝置。
- `讀取長度` 預設 64（full-speed HID 報告上限）；若你的裝置報告較長請自行調大。

### 「開啟後馬上 Input 讀取停止：read error」—— 多半是正常的，尤其 HID Power Device

`dev.read()` 讀的是 **Input report（中斷 IN pipe）**。讀不到時要先分清楚兩件事：

1. **這顆是 HID Power Device / UPS（report descriptor 含 usage page `0x84`）**：
   Windows 的 `hidbatt` 驅動會接管它的 Input report 串流，所以使用者程式 `read()` 不到
   Input report。**這是 OS 的正常行為、不是故障**，更不該為了讀 Input 把 UPS 功能拿掉。
   重點是 **Output report 與 Get/Set Feature（走 control pipe）仍然完全可用** —— 改用右側功能、
   填對 Report ID 即可（此類裝置一律用 numbered report）：
   - `Get Feature` + Report ID = `06` / `0C` → 讀 UPS 容量 / 狀態（mWh）
   - `Get Feature` + Report ID = `F1`（長度 64）→ vendor OTA 狀態
   - `Get Feature` + Report ID = `F2` / `F3`（長度設 **33**，不是 64）→ 韌體版本字串
   - `Output report` + Report ID = `F0` → vendor OTA 命令

   只有「真的需要在 user space 收非同步 Input report」時，才需要把 vendor 通道改到
   獨立 USB interface / 獨立 IN 端點；一般讀值與 OTA 都靠 Feature 輪詢，不需要 Input。

2. **不是 Power Device、但 read 失敗**：`read` 失敗不代表 `write` / Feature 也失敗。先確認
   Report ID 與長度有沒有填對再用 Output / Get/Set Feature。若三者全失敗才考慮：被其他程式
   佔用、是系統 HID（鍵盤 / 滑鼠，Windows 本來就獨佔輸入），或裝置已拔除。

> Feature report 的 `read error` 常常只是 Report ID 填成 `0`／長度不符。numbered report 裝置
> 必須填實際的 Report ID（例如 `F1`），且 `F2`/`F3` 這種要剛好 33 bytes，用 64 會讀失敗。
