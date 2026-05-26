# Serial Port Tool

Qt6 (PySide6) + pyserial 寫的 COM port GUI 測試工具。Layout 參考常見「串口測試」工具：左側大接收區、右側窄控制區。

## 功能

- 掃描所有 COM port，下拉顯示完整描述（device、description、manufacturer、hwid）
- 連線參數可調：baud / data bits / parity / stop bits
- HEX 傳送：接受 `01 AB 99`、`01ab99`、`01-AB-99`、`01,AB,99` 等大小寫與分隔混合
- ASCII 傳送：結尾可選 `無 / \r / \n / \r\n`
- 連續傳送模式（HEX 或 ASCII 擇一，共用一個 ms 間隔）
- 接收三分頁：ASCII / HEX / 對照（hex dump）
- HEX 與 ASCII 輸入框是 editable combobox，自動保留歷史命令
- 「停止顯示」勾選暫停 UI 更新，計數仍背景累加
- 「記錄行數」可調整接收區最大保留行數
- 工具選單內建程式設計師計算機（HEX/DEC/OCT/BIN + 位元運算）

## 執行

```powershell
pip install -r requirements.txt
python main.py
```

需要 Python 3.9 以上。

## 快捷鍵

- `F5`：重新掃描通訊埠
- `Ctrl+K`：開啟程式設計師計算機
- 在 HEX / ASCII 輸入框按 `Enter`：直接觸發單筆傳送
