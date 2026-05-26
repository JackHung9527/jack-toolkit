# Network Scanner

純 Python 3 + tkinter，無第三方依賴。仿 MobaXterm 的三個工具：

1. **IP Range Scan** — 對一段 IPv4 (e.g. `192.168.1.1` -> `254`) 做 ping sweep + 常見埠 (SSH/RDP/VNC/FTP/Telnet/Rlogin/HTTP/HTTPS) 探測。
2. **Port Scan** — 對單一 target 掃任意 port 範圍 (1..65535)，列出 open ports + 服務名稱猜測。
3. **Ping Monitor** — 對單一 host 連續 ping，按時間軸記錄每筆 OK / FAIL + RTT，自動偵測 UP↔DOWN 狀態轉換並統計掉線時長；可即時寫入 log 檔。

## 啟動

雙擊 `run.bat`，或直接：

```powershell
python network_scanner.py
```

## 操作

- **IP Range Scan**：填三段 octet + 末段起訖，按 **Start scan**；表格即時更新。
  - 左鍵雙擊一行 → 帶 IP 到 **Port Scan** 分頁
  - 右鍵點一行 → 帶 IP 到 **Ping Monitor** 分頁
- **Port Scan**：填 target IP / hostname + port 範圍。預設 Timeout 300ms / 200 threads，掃 1-1024 約 2~5 秒；掃 1-65535 約 1-3 分鐘 (依網路延遲與 firewall 行為)。
- **Ping Monitor**：填 target、Interval (秒，預設 1.0) 與 Timeout (毫秒，預設 1000)，按 **Start**。
  - 每筆 ping 結果一行：`Time / Status / RTT(ms) / Streak / Note`
  - 狀態轉變 (UP→DOWN, DOWN→UP) 整行反白並在 Note 標註「DOWN after 12.3s UP」之類的持續時間
  - 統計列即時更新：`Total / OK / Fail / Loss% / Max-down-streak / Current` (目前是 UP 還是 DOWN，已持續多久)
  - 勾 **Save log** + Browse 可選 log 檔位置；不點 Browse 就用 script 同目錄 `ping_<ip>_<timestamp>.log` (line-buffered append，crash safe)
  - 勾 **Only state changes**：表格只記狀態轉變那幾筆 (log 檔仍寫全部)
  - **Clear** 清表 + 重置統計；**Export...** 把目前表格內容另存
- Stop / Stop scan 隨時可中斷。

## 注意

- 走 ICMP ping (Windows `ping -n 1 -w`) 判活，部分主機會 ICMP block；若 ICMP 不通但有 TCP 開埠，仍會列出。
- TCP 探測用 `socket.connect_ex`，不送 packet payload，被 IDS 視為正常 connect。
- 對非自家網段做大量掃描在多數企業環境是違規行為，請只對自己有權限的網段操作。
