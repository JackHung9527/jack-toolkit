# FT232H 測試器 (FT232H Tester)

FT232H USB 轉 GPIO / SPI / I2C 模組的桌面測試工具。Python + tkinter。

## 功能

- 自動掃描已連接的 FT232H 裝置（依 USB 序號區分多顆）
- **GPIO 分頁**：16 個 pin（AD0–AD7、AC0–AC7）各別設方向、寫值、即時讀回（可 200ms 自動 poll）
- **SPI 分頁**：CS0–CS4、mode 0/1/2/3、頻率可調、支援 Write / Read / Exchange（含 full-duplex）
- **I2C 分頁**：100 k / 400 k / 1 M Hz、bus scan、register 與 raw read/write
- 共用 hex 輸入解析（`DE AD BE EF`、`deadbeef`、`0xDE,0xAD` 皆可），來自 `common/hex_utils.py`
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
> `tools/install_driver.ps1` 內有自動下載 Zadig 的腳本可參考。

## 執行

從 jack-toolkit 根目錄安裝依賴後直接執行：

```powershell
# 在 jack-toolkit/ 根目錄
pip install -r requirements.txt
python tools/ft232h/main.py
```

或從 launcher 啟動：

```powershell
python launcher.py
```

需要 Python 3.9 以上。

## 專案結構

```
ft232h/
├── main.py                 # 入口（套用 libusb backend fix 後啟動 MainWindow）
├── manifest.json
├── README.md
├── src/
│   ├── core/
│   │   ├── device.py       # 裝置掃描 / URL 管理
│   │   ├── gpio_ctrl.py    # 16-bit GPIO 控制
│   │   ├── spi_ctrl.py     # SPI master
│   │   └── i2c_ctrl.py     # I2C master
│   └── ui/
│       ├── main_window.py  # 主視窗 + 分頁框架
│       ├── gpio_tab.py
│       ├── spi_tab.py      # 使用 common.hex_utils
│       ├── i2c_tab.py      # 使用 common.hex_utils
│       └── log_panel.py    # 共用 log widget
└── tools/
    └── install_driver.ps1  # 自動下載 Zadig 換 driver 的輔助腳本
```

## 已知限制

- 一個 FT232H 同一時間只能跑 **一種** MPSSE 模式（GPIO、SPI、I2C 互斥）。切協議必須先按該分頁的 **Close**，再到另一個分頁按 **Open**。
- I2C 必須外接 pull-up，否則 `Scan bus` 不會有任何結果或讀到全 0xFF。
- 多顆 FT232H 同時插入時，FT232H 的 EEPROM 必須先燒入不同序號（用 FT_Prog），不然兩顆會搶用同一個 URL。
