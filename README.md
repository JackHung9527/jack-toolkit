# jack-toolkit

個人萬用工具集合 — 把日常會用到的桌面 GUI 小工具放在同一個 repo，未來會用一個 launcher 主視窗加選單切換各工具。

目前收錄三個獨立工具，每個都可單獨執行；統一的 launcher 介面在開發中。

## 收錄工具

| 子目錄 | 工具 | 用途 | 框架 |
|---|---|---|---|
| [tools/serial/](tools/serial/) | Serial Port Tool | COM port 收發、HEX/ASCII 雙模式、連續傳送、程式設計師計算機 | PySide6 (Qt6) |
| [tools/netscan/](tools/netscan/) | Network Scanner | IP range ping sweep、port scan、ping monitor with 狀態統計 | tkinter |
| [tools/ft232h/](tools/ft232h/) | FT232H Tester | FT232H USB-to-GPIO/SPI/I2C 桌面測試介面 | tkinter |

## 目錄結構

```
jack-toolkit/
├── README.md                # 本檔
├── .gitignore
├── requirements.txt         # 全部工具依賴聯集（tkinter 為內建不列）
├── launcher.py              # (待開發) 統一主視窗 + 選單切換
└── tools/
    ├── serial/              # Serial Port Tool (PySide6)
    │   ├── main.py
    │   ├── README.md
    │   └── requirements.txt
    ├── netscan/             # Network Scanner (tkinter)
    │   ├── network_scanner.py
    │   ├── README.md
    │   └── run.bat
    └── ft232h/              # FT232H Tester (tkinter + pyftdi)
        ├── main.py
        ├── README.md
        ├── requirements.txt
        ├── run.ps1
        ├── build_exe.ps1
        ├── ft232h_tester.spec
        ├── src/
        └── tools/
```

## 各工具獨立執行

每個工具的子目錄都保留自己的 README 與啟動方式。最簡單：

```powershell
# Serial Port Tool
cd tools\serial
pip install -r requirements.txt
python main.py

# Network Scanner
cd tools\netscan
python network_scanner.py
# 或雙擊 run.bat

# FT232H Tester
cd tools\ft232h
.\run.ps1
# 或： pip install -r requirements.txt; python main.py
```

## Roadmap

- [ ] 寫一個 `launcher.py` 主視窗，用選單或側邊欄切換各工具
- [ ] 決定 UI 框架統一方向（tkinter 兩個工具改寫成 PySide6，或保留 tkinter 各跑各的）
- [ ] 共用 hex parse / ASCII helper 抽出到 `common/`
- [ ] 之後可能加入：CAN monitor、I2C/SPI sniffer (FT232H 強化版)、JTAG/SWD console、Modbus master

## 環境

- Python 3.9 以上（PySide6 6.5 起）
- Windows 為主要測試平台
