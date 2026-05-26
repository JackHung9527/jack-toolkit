# FT232H Tester

FT232H USB 轉 GPIO / SPI / I2C 模組的桌面測試工具。
以 Python + Tkinter 撰寫，可直接執行原始碼，也可用 PyInstaller 打包成單檔 `.exe`。

## 功能

- 自動掃描已連接的 FT232H 裝置（依 USB 序號區分多顆）
- **GPIO 分頁**：16 個 pin（AD0–AD7、AC0–AC7）各別設方向、寫值、即時讀回（可 200ms 自動 poll）
- **SPI 分頁**：CS0–CS4、mode 0/1/2/3、頻率可調、支援 Write / Read / Exchange（含 full-duplex）
- **I2C 分頁**：100 k / 400 k / 1 M Hz、bus scan、register 與 raw read/write
- 共用 hex 輸入解析（`DE AD BE EF`、`deadbeef`、`0xDE,0xAD` 皆可）
- 底部 log 視窗：含時間戳、INFO / OK / WARN / ERR 顏色標記

## FT232H pinout 速查

| 用途 | 腳位 |
|---|---|
| SPI SCK   | AD0 |
| SPI MOSI  | AD1 |
| SPI MISO  | AD2 |
| SPI CS0–CS4 | AD3 / AD4 / AD5 / AD6 / AD7 |
| I2C SCL   | AD0 |
| I2C SDA   | **AD1 與 AD2 必須短接**（FT232H 無真正 open-drain，須外接 4.7 kΩ pull-up 到 VCC） |
| GPIO      | 未被上述協議占用的 AD/AC 腳位皆可（共 16 bit） |

## 安裝 driver（Windows 必做）

FT232H 出廠 driver 是 FTDI VCP（虛擬序列埠），`pyftdi` 走的是 libusb，必須先換 driver：

1. 下載 [Zadig](https://zadig.akeo.ie/)（單一 exe）
2. 把 FT232H 板子用 USB 接上電腦
3. 開啟 Zadig → 上方選單 **Options → List All Devices** 勾起來
4. 下拉選單找到 `FT232H` 或 `USB Serial Converter`
5. 右側 driver 選 **libusbK**（或 `WinUSB`），按 **Replace Driver**
6. 完成後可在裝置管理員中看到 `libusbK USB Devices → FT232H`

> 如果同一台板子上的 FT232H 之後還要在 Arduino IDE / FTDI VCP 用，可在裝置管理員把 driver 換回 `FTDI USB Serial`，要回 libusb 再用 Zadig 切回去。

## 從原始碼執行（開發模式）

需求：Python 3.9+

```powershell
# Windows PowerShell
.\run.ps1
```

第一次執行會自動建立 `.venv` 並安裝相依套件。之後再執行就直接啟動。

手動模式：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 打包成 .exe

```powershell
.\build_exe.ps1
```

產出位置：`dist\FT232H_Tester.exe`（單檔，雙擊即可開啟）。

打包腳本會：

1. 建立或重用 `.venv`
2. 安裝 `requirements.txt`
3. 清掉舊的 `build/` 與 `dist/`
4. 用 `ft232h_tester.spec` 跑 PyInstaller（已內建 libusb-package 的 DLL 與 pyftdi 的 data files）

預設 `console=False`（純 GUI，不開 console 視窗）。若要看 stderr 訊息，把 `ft232h_tester.spec` 內 `console=False` 改為 `True` 再重打包。

## 專案結構

```
FT232H/
├── main.py                  # 入口（同時用於開發與 PyInstaller）
├── requirements.txt
├── ft232h_tester.spec       # PyInstaller spec
├── build_exe.ps1            # 一鍵打包
├── run.ps1                  # 一鍵啟動（開發）
├── src/
│   ├── core/
│   │   ├── device.py        # 裝置掃描 / URL 管理
│   │   ├── gpio_ctrl.py     # 16-bit GPIO 控制
│   │   ├── spi_ctrl.py      # SPI master
│   │   └── i2c_ctrl.py      # I2C master
│   └── ui/
│       ├── main_window.py   # 主視窗 + 分頁框架
│       ├── gpio_tab.py
│       ├── spi_tab.py
│       ├── i2c_tab.py
│       ├── log_panel.py     # 共用 log widget
│       └── hexutil.py       # hex 字串解析
└── README.md
```

## 已知限制

- 一個 FT232H 同一時間只能跑 **一種** MPSSE 模式（GPIO、SPI、I2C 互斥）。切協議必須先按該分頁的 **Close**，再到另一個分頁按 **Open**。
- I2C 必須外接 pull-up，否則 `Scan bus` 不會有任何結果或讀到全 0xFF。
- 多顆 FT232H 同時插入時，FT232H 的 EEPROM 必須先燒入不同序號（用 FT_Prog），不然兩顆會搶用同一個 URL。

## 授權

MIT
