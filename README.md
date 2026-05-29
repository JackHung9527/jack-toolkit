# jack-toolkit

個人萬用工具集合 — 把日常會用到的桌面 GUI 小工具放在同一個 repo。所有子工具皆為獨立程序、統一使用 tkinter，最上層的 `launcher.py` 是一個 tkinter dashboard，自動掃描 `tools/*/manifest.json`，按下啟動就 spawn 一個獨立 process；launcher 自己不關閉，可同時開多個工具。

## 收錄工具

| 子目錄 | 工具 | 用途 | 框架 |
|---|---|---|---|
| [tools/serial/](tools/serial/) | 串列埠工具 | COM port HEX/ASCII 雙模式收發、連續傳送、內建程式設計師計算機 | tkinter |
| [tools/netscan/](tools/netscan/) | 網路掃描器 | IP range ping sweep、port scan、ping monitor 含狀態統計 | tkinter |
| [tools/ft232h/](tools/ft232h/) | FT232H 測試器 | FT232H USB 轉 GPIO/SPI/I2C 桌面測試介面 | tkinter |

## 目錄結構

```
jack-toolkit/
├── README.md                   # 本檔
├── .gitignore
├── requirements.txt            # 所有工具共用的依賴清單
├── launcher.py                 # tkinter dashboard，掃 manifest 自動列出工具
├── common/                     # 三支共用模組（純邏輯，不綁 GUI）
│   ├── __init__.py
│   └── hex_utils.py            # HEX / ASCII / hex dump helper
└── tools/
    ├── serial/                 # 串列埠工具 (tkinter + pyserial)
    │   ├── main.py
    │   ├── manifest.json
    │   └── README.md
    ├── netscan/                # 網路掃描器 (tkinter + stdlib)
    │   ├── network_scanner.py
    │   ├── manifest.json
    │   └── README.md
    └── ft232h/                 # FT232H 測試器 (tkinter + pyftdi)
        ├── main.py             # 入口（含 libusb backend fix）
        ├── manifest.json
        ├── README.md
        ├── src/
        │   ├── core/           # device / gpio / spi / i2c 控制
        │   └── ui/             # 主視窗 + 三分頁 + log panel
        └── tools/
            └── install_driver.ps1  # 自動下 Zadig 換 driver
```

## 安裝依賴

從 repo 根目錄一次裝完全套：

```powershell
pip install -r requirements.txt
```

`tkinter` 是 Python 內建不列入，`netscan` 純標準函式庫也無第三方依賴；`serial` 需要 `pyserial`，`ft232h` 需要 `pyftdi / pyusb / libusb-package`。

## 使用 launcher 啟動

```powershell
python launcher.py
```

或直接雙擊根目錄的 [launcher.bat](launcher.bat)（優先 `pythonw.exe` 跑，沒有黑色 console window）。

launcher 視窗會列出所有工具卡片，點「啟動」即可在獨立 process 開啟對應工具，可重複啟動或同時開多個。右側「執行中」面板列出活著的子程序與 PID，按「終止」可關掉單一工具。

## 各工具獨立執行

每支工具的 entry 都能單獨跑，不一定要走 launcher：

```powershell
python tools/serial/main.py
python tools/netscan/network_scanner.py
python tools/ft232h/main.py
```

## 新增工具

只要在 `tools/<name>/` 放一份 `manifest.json`：

```json
{
  "name": "myTool",
  "display_name": "我的工具",
  "description": "一行說明",
  "entry": "main.py",
  "framework": "tkinter",
  "requirements": null
}
```

launcher 下次啟動會自動掃到。若需要共用的 HEX / ASCII / hex dump helper，從 `common.hex_utils` import。

## 打包成單一 exe（未來規劃）

`launcher.py` 已預留 `--tool <name>` dispatch 路徑：

```powershell
python launcher.py --tool serial    # 直接以 serial 為入口執行
```

打包成 `launcher.exe` 後，「啟動」按鈕會偵測到 frozen，自動 spawn `launcher.exe --tool <name>` 重入到該工具，所以一份 exe 即可承載整套。實際 PyInstaller spec 之後再做（需 hidden-import 每支工具的依賴）。

## Roadmap

- [x] `launcher.py` 主視窗（tkinter dashboard + 子程序模型 + manifest 自動掃描）
- [x] 統一 framework：全部 tkinter，避開 Qt / Tk event loop 衝突
- [x] 共用 hex parse / ASCII helper 抽到 `common/`
- [x] 單一 root requirements，子工具 requirements 整併
- [ ] PyInstaller 打單一 exe（spec 與 hidden-import 撰寫）
- [ ] launcher 顯示工具圖示 / 分類群組
- [ ] 之後可能加入：CAN monitor、I2C/SPI sniffer（FT232H 強化版）、JTAG/SWD console、Modbus master

## 環境

- Python 3.9 以上
- 主要在 Windows 11 + PowerShell 開發與測試
