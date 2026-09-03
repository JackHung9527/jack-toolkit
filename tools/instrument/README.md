# 儀器控制台 instrument

通用型儀器控制介面。用 [PyVISA](https://pyvisa.readthedocs.io/) 作統一後端，一套 UI 就能
操作四種實體介面，下簡單的文字命令（SCPI 等），命令結尾是否要加 `\r\n` 完全可設定。

## 功能

- **四種介面統一操作**
  | 介面 | VISA 資源字串範例 | 備註 |
  |---|---|---|
  | USB-TMC | `USB0::0x0957::0x1798::MY52345678::INSTR` | 按「掃描儀器」自動列舉 |
  | RS232 (串列) | `ASRL3::INSTR`（對應 COM3） | 可設鮑率 / 資料 / 校驗 / 停止位元 |
  | LAN (乙太網路) | `TCPIP0::192.168.1.100::INSTR` (VXI-11)<br>`TCPIP0::192.168.1.100::5025::SOCKET` (raw)<br>`TCPIP0::192.168.1.100::hislip0::INSTR` (HiSLIP) | 填 IP 即可，協定可選 |
  | GPIB | `GPIB0::12::INSTR` | 需系統 VISA + GPIB 卡驅動 |
  | 手動輸入 | 任意合法 VISA 資源字串 | 進階用 |

- **命令三種送法**
  - **送出 Write**：只送命令、不讀回應（例：`*RST`、`OUTP ON`）
  - **查詢 Query**：送命令再讀一筆回應，並顯示往返耗時（例：`*IDN?`、`MEAS:VOLT?`）
  - **讀取 Read**：只讀一筆（配合先前的 Write 使用）
  - 命令列按 Enter：結尾是 `?` 自動走 Query，否則 Write

- **命令結尾可自由設定**（本工具核心）
  - **傳送結尾**（`write_termination`）：`無 / \n / \r / \r\n`，命令送出時自動附加在尾端
  - **接收結尾**（`read_termination`）：`無 / \n / \r / \r\n`，Query/Read 收到此字元即視為一筆回應結束
  - 兩者連線中即時可改，不必重連

- 逾時（timeout, ms）可調；後端可選 `自動 / pyvisa-py / 系統 VISA`
- 掃描列舉目前連著的儀器；命令歷史下拉重送；常用命令快捷鈕（`*IDN?`、`*RST`、`SYST:ERR?`…）
- 收發記錄（送出藍、回應綠、錯誤紅）附時間戳，可複製
- 所有 VISA I/O 都跑在背景 worker thread，UI 永不凍結（query 逾時也不卡死視窗）

## 依賴

```powershell
pip install pyvisa pyvisa-py
# 選配（讓「掃描」對 LAN VXI-11/HiSLIP 自動探索生效；不裝也能手動填 IP）
pip install psutil zeroconf
```

- `pyvisa-py` 是純 Python 後端，USB-TMC 靠 `pyusb + libusb-package`（本 repo 已為 ft232h 裝過）、
  RS232 靠 `pyserial`（本 repo 已為 serial 裝過），所以 USB / 串列 / LAN 免裝任何原廠 VISA 即可用。
- **GPIB** 需要系統 VISA（NI-VISA / Keysight IO Libraries）或 linux-gpib；後端請選「系統 VISA (@ivi)」。
- 若已安裝 NI-VISA 等原廠 VISA，後端選「自動」會優先用它（USB/LAN/GPIB 全支援）。

## 執行

```powershell
python main.py
```

或雙擊本目錄的 `儀器控制台.bat`（優先 pythonw，無 console 視窗）。也可經 jack-toolkit
launcher 啟動（本目錄含 manifest.json）。

## 使用流程

1. 選「介面類型」，填對應欄位（USB/GPIB 可按「掃描儀器」自動帶入資源字串）。
2. 確認「VISA 資源」字串無誤，設好逾時與後端，按「連線」。
3. 按「*IDN? 辨識」確認通訊正常。
4. 在「命令」列輸入命令，按 Write / Query / Read；用上方「傳送結尾」切換要不要加 `\r\n`。

## 常見問題

- **Raw Socket 連得上但 Query 一直逾時**：raw socket 沒有 EOI，一定要把「接收結尾」設成儀器
  實際送回的結尾（多半是 `\n`），否則會讀到逾時。
- **USB-TMC 掃到卻連不上 / 權限錯誤**：pyvisa-py 走 libusb，Windows 上該裝置需為 WinUSB/libusb
  驅動（可用 Zadig 換）；若裝的是原廠驅動，改用該廠 VISA（後端選「系統 VISA」）較穩。
- **GPIB 掃不到**：pyvisa-py 對 GPIB 支援有限，請安裝原廠 VISA 並把後端切成「系統 VISA (@ivi)」。
