# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案性質

`jack-toolkit` 是一個 Python tkinter 桌面工具 monorepo，加上一個獨立的 STM32 韌體子專案。所有溝通與註解一律用繁體中文（見全域 `~/.claude/CLAUDE.md`）。

## 常用指令

```powershell
# 安裝依賴（必須走系統 python，不要走 venv — 雙擊 .bat 用的是系統 python）
.\install_requirements.bat
# 或顯式指定 python
python -m pip install -r requirements.txt

# 啟動 launcher（雙擊或 PowerShell）
.\launcher.bat               # 優先 pythonw（無 console），失敗自動 messagebox
python launcher.py           # 開發時用，stderr 直接看得到

# 單獨跑某個工具（不經 launcher）
python tools/serial/main.py
python tools/netscan/network_scanner.py
python tools/ft232h/main.py

# launcher 內部 dispatch（給 PyInstaller frozen exe 重入）
python launcher.py --tool <name>

# FT232H 換 driver（Windows 必做一次）
.\install_ft232h_driver.bat  # UAC 提權後跑 tools/ft232h/tools/install_driver.ps1
```

無 lint / test 設置；專案以「能跑」為驗收標準，UI 變動需實機開來操作確認。

## 架構（big picture）

### Launcher 模型 — [launcher.py](launcher.py)

關鍵設計：**每個工具是獨立 subprocess**，launcher 自己永遠不死。

- 啟動時 `discover_tools()` 掃 `tools/*/manifest.json`（不在 manifest 的目錄會被忽略——例如 `tools/CommBench/` 沒 manifest，launcher 看不見它，這是刻意的）。
- 按「啟動」→ `subprocess.Popen([sys.executable, str(tool.entry)], cwd=tool.cwd)`，**抓 stderr** 給崩潰時顯示。
- 每 500 ms `_poll_processes()` 檢查子程序退出碼，非 0 就把 stderr 餵進 messagebox，並偵測 `ModuleNotFoundError` 給出對應 pip 指令。
- Frozen (PyInstaller) 模式：`launcher.exe --tool <name>` 是 dispatch 入口，按鈕會 spawn 自己重入。Source 模式：直接 spawn 子工具 entry。`_spawn_command()` 是分流點。

**新增工具就是放一個 `tools/<name>/manifest.json`**（schema 見 [README.md](README.md)），不用改 launcher。

### 共用模組 — [common/hex_utils.py](common/hex_utils.py)

只有 HEX/ASCII parse/format/dump。serial 與 ft232h 都從這 import。新增共用邏輯一律放這，不要在子工具間複製。`bytes_to_ascii_inline_segments()` 回傳 `(text, is_escape)` tuple 給 GUI 上色用，避免使用者資料裡的 `\r` 字面字串跟 CR 跳脫顯示混淆。

### 子工具

| Tool | Entry | 特殊事項 |
|---|---|---|
| serial | [tools/serial/main.py](tools/serial/main.py) | pyserial；HEX/ASCII 雙模收發 |
| netscan | [tools/netscan/network_scanner.py](tools/netscan/network_scanner.py) | 純 stdlib，無第三方依賴 |
| ft232h | [tools/ft232h/main.py](tools/ft232h/main.py) | **見下方 libusb fix**，pyftdi/pyusb/libusb-package |

### FT232H libusb backend fix — 改 ft232h 前必讀

[tools/ft232h/main.py](tools/ft232h/main.py) 的 `_setup_libusb_backend()` 套了三組 fix，**順序與內容都不能隨便動**：

1. **DLL 路徑**：把 `libusb_package` 帶的 `libusb-1.0.dll` 放進 PATH + `os.add_dll_directory`，避開 `C:\Windows\system32\libusb0.dll` 殘留（libusb-win32 舊版，跟 WinUSB driver 不相容）。
2. **強制 backend**：monkey-patch `pyftdi.usbtools.UsbTools._load_backend`，用 `libusb_package.find_library` 解析的 backend，否則 pyftdi 預設可能撿到錯的 DLL。
3. **縮減 PRODUCT_IDS**：把 `Ftdi.PRODUCT_IDS` 砍到只剩 `0x6014`（FT232H），避免 enumerate 時對機器上其他 FTDI device（例如 FT232R 在跑 FTDIBUS driver）做 `libusb_open` 噴 `NotImplementedError` 把整個流程拖死。

每組 fix 都用 `try/except Exception: pass` 包起來，避免 dev 機沒裝 libusb-package 時整個 app 起不來。改動這段時保留這個 fallback 邏輯。

`src/core/device.py` 的 `_reset_all_ft232h()` 額外處理「FT232H 在 Zadig 換 driver 後 GET_DESCRIPTOR timeout」的「半死狀態」，每次掃 device 前都會跑一次，對正常 device 無害。

### Launcher 錯誤可見性原則（必讀）

歷史踩雷：用 `pythonw.exe` 跑時 stderr 被吃掉，未捕捉例外會「靜默死掉」毫無線索。所以 [launcher.py](launcher.py) **在所有其他 import 之前**裝 `sys.excepthook` 寫 `launcher_error.log` + 跳 tkinter messagebox。

**任何新加的 Windows launcher script（.bat/.ps1/.sh）都必須保有錯誤可見路徑**——pythonw / 重導 stderr / `start ""` 都會吃錯誤，要有 fallback。`install_requirements.bat` 的設計是顯式呼叫 `python.exe -c "import sys; print(sys.executable)"` 印出實際用到的 python，避免裝到錯的解譯器。

## CommBench 子專案（特例，非 Python 工具）

[tools/CommBench/G071_NUCELO_CommBench/](tools/CommBench/G071_NUCELO_CommBench/) 是一個 **STM32 G071 NUCLEO CubeIDE Makefile 韌體專案**，不是 Python 工具，launcher 不會看見它（沒 manifest）。用途：萬用通訊測試板（CLI、SCPI、I2C DUT 等）。

- 框架見 `USER_CODE/README.md`：三層狀態機（task / flow / process）裸機規範，所有 driver 用獨立 subfolder + `subfolder/driver.h` 引用方式。
- 修改韌體時請走 `firmware-project-builder` agent 或 `stm32-*-scaffold` 系列 skill，不要手 patch USER_CODE/ 框架檔。
- CubeMX 慣例：**不勾 per-peripheral .c/.h**（沒有 `i2c.h`/`usart.h`），所有 peripheral init 集中在 `main.c`，driver 用 `extern` 拉 HAL handle。

## 環境

- Python 3.9+，Windows 11 + PowerShell 為主要開發環境。
- bash 工具下的 `python` 常常是 venv，跟使用者雙擊 .bat 用的系統 python 是兩顆——`pip install` 驗證時要顯式指定路徑。

---

## 今日總結

### 2026/07/16

#### 完成項目
- 校正設計工具（`tools/calib_designer/`）新增「目標值為 0 的點一律排除」：相對誤差以目標值為分母，y=0 會除以近零把誤差炸掉。做法是 engine 新增 `is_excluded()` + `_filter_calc()`，所有配點演算法（greedy / dp / uniform / min_nodes）改成 wrapper——先濾掉 y=0 的點再配點、回傳的節點索引再映射回原始曲線，確保 y=0 永不被選為節點；頭尾自動改用第一個/最後一個非零點
- 誤差評估對 y=0 的點回傳 NaN（`_errors`），彙總用 `_agg()` 過濾 NaN 算 max/RMS，繪圖時 matplotlib 自動在該點斷線；手動插點與回歸取樣點都擋掉 y=0 的列；線性回歸擬合也排除 y=0
- 逐點比較數據表可右鍵複製整表（或按「複製到剪貼簿」鈕）：整表以 Tab 分欄、換行分列丟進剪貼簿，貼到 xlsx 自動落格
- 回歸取樣點數改為鎖定＝LUT 節點數（移除原本可自由拖的滑桿），只保留「同內插節點 / 均勻同點數」兩種撒點方式的單選；節點欄改顯示回歸實際取用的點
- 逐點比較表由三方擴成四方：原始 / 內插(演算法) / 內插(均勻) / 線性回歸，新增「均點」標記與「均勻計算值 / 均勻誤差」欄、四方最佳評比，並加水平捲軸容納變寬欄位
- 重新設計圖示：`make_icon.py` 在卡片右下角加紅色 "V2"（白色描邊，48px 小圖仍可辨識）；UI 視窗標題改「校正設計工具 V2」
- 用系統 Python 3.12（PyInstaller 6.21 / matplotlib 3.11 / numpy 2.4）重新打包 `dist/校正設計工具.exe`（38.2 MB），實機啟動確認標題列「校正設計工具 V2」+ UI 全渲染正常

#### 問題與踩坑
- **PyInstaller 不能排除 PIL**：matplotlib 3.11 的 `colors.py` 在 import 期就 `from PIL import Image`（非 try/except），所以 `--exclude-module PIL` 會讓 matplotlib 整包 import 失敗、frozen exe 一啟動就崩潰。第一次打包貪圖省 6 MB 加了 `--exclude-module PIL`（32.1 MB），結果 exe 崩潰。移除該排除、改回原本排除清單（scipy/pandas/lxml/openpyxl/Qt/wx）才恢復正常（38.2 MB）。工具本身雖沒 import PIL，但 matplotlib 硬相依，不可砍
- onefile 模式下 `main.py` 的 `calib_designer_error.log` 因 `Path(__file__).parent` 指向 `_MEIPASS` 暫存解壓區，崩潰後隨程序結束刪除，所以「看不到 error log」不代表沒崩潰；改用「process 是否存活 + PrintWindow 依 HWND 截圖」判斷 exe 生死
- 相對誤差用 `max(abs(y), eps)` 只是避免除零，但 y=0 時仍會回傳巨大誤差主導 minimax、逼演算法把節點浪費在零點；改用 NaN sentinel 徹底排除才對
- 逐點比較表是 `tk.Label` 一格格 grid（為了只給「最佳」欄上色），無原生選取；右鍵複製改用「建整表 TSV → 塞剪貼簿」，並在每個 cell 綁 `<Button-3>` 才能任一格叫出選單

### 2026/07/14

#### 完成項目
- 把 `tools/calib_designer/`（校正設計工具）用 PyInstaller 單獨打包成 standalone `.exe`：`--onefile --windowed`、內嵌 `calib_designer.ico`，目標機免裝 Python / matplotlib，雙擊即開
- 用有裝 matplotlib 3.11 + numpy 2.4 + PyInstaller 6.21 的系統 Python 3.12 打包；ico 一併 `--add-data` 進 bundle
- 排除 venv 裡 matplotlib 自動拖入但工具沒用到的套件（scipy / pandas / lxml / openpyxl / Qt / wx），把 exe 從 79.7 MB 砍到 38.1 MB、建置時間也少一半
- 實測啟動 + PrintWindow 依 HWND 截圖驗證：資料表格、校正方式、LUT 節點選法、matplotlib 比較圖與誤差子圖全渲染正常，中文標籤無豆腐方塊
- 產物落在 `tools/calib_designer/dist/校正設計工具.exe`，已被既有 `.gitignore`（`dist/` `build/` `*.exe`）忽略，不進版控

#### 問題與踩坑
- venv Python 的 matplotlib PyInstaller hook 會自動探測並拖入 scipy / pandas / lxml / openpyxl / PIL 等「已安裝但工具沒 import」的套件，導致 onefile 肥大又拖慢啟動；工具實際只 import `csv / math / tkinter / matplotlib`，用 `--exclude-module` 砍掉這些屬零風險，直接砍半
- onefile 模式下 `main.py` 的 `Path(__file__).resolve().parent` 指向 `_MEIPASS` 解壓暫存目錄；把 ico 用 `--add-data "calib_designer.ico;."` 放進 bundle 根，執行期 `iconbitmap` 就抓得到，視窗標題列圖示正常，不必改原始碼
- onefile 會有 bootloader 父/子兩個同名 process，父 process 的 `MainWindowTitle` 為空；smoke test 要挑 `MainWindowHandle != 0` 的子 process 才抓得到視窗做截圖驗證

### 2026/07/08

#### 完成項目
- 編譯 + 燒錄 G071 CommBench 韌體，並產出一套「以後自己燒」的工具夾 `tools/CommBench/G071_NUCELO_CommBench/TOOLS/flash_via_stlink/`
- 專案原本沒有 `Debug/`（從沒編譯過），用 STM32CubeIDE 1.16.0 headless `-import` + `-cleanBuild` 產生 Makefile 並編譯（0 errors 0 warnings，text=44408/data=92/bss=13764）
- CommBench makefile 只產 .elf，照既有踩坑筆記由最新 .elf 強制 objcopy 重生 .hex/.bin（避開 stale-hex）
- 燒錄明確指定 `sn=0667FF504857788667165423`（NUCLEO-G071RB）+ `--verify`，`Download verified successfully`，避免誤燒同時接著的 H7 板（SN `53FF74068678574858450267`）
- 自助燒錄工具（stm32-stlink-flash skill 客製版）：雙擊 flash.bat 即燒，自動找 STM32_Programmer_CLI、自動挑 hex/ 內日期最新的 .hex、一律 program+verify、燒完 reset

#### 問題與踩坑
- 環境有兩顆 ST-Link，原 skill 模板遇多顆會直接 exit 7 罷工且不帶 `sn=`；客製成「用 Board Name 鎖定 NUCLEO-G071 並把 sn= 帶進每個 CLI 呼叫」，找不到目標就報錯停下，永不誤觸 H7
- Write 工具產出無 BOM，含中文的 program.ps1 在 PowerShell 5.1 被 cp950 誤讀導致 parser 崩（missing terminator）；後處理轉 UTF-8 with BOM 解決（既有記憶 feedback_ps51_chinese_ps1_bom 已載）
- config.ini 的 `[target]` 區段標頭一開始只寫在註解裡漏掉真正的 header，害 TARGET_BOARD 被歸到 [programmer] 區段；補上真正的 `[target]` 標頭
- 加的 verify-only 旁支因 STM32_Programmer_CLI 的 `-v` 必須跟在 `-w` 後（不能單獨驗證）而報錯；直接移除該旁支，改成永遠 program+verify
- headless import 動到 `.settings/language.settings.xml` 的 env-hash（IDE metadata 雜訊），已還原

### 2026/06/30

#### 診斷項目（無程式碼變更）
- 排查使用者「乙太網路 metric 改 9000 隔天又變回預設」問題，確認與桌面 `回公司-claude.bat` / `外面-claude.bat` 無關——那兩個檔只切 proxy + 重啟 Tailscale + 寫 mode.txt，完全不碰 interface metric
- 鎖定真因：出問題的是 **Realtek USB GbE**（idx17）。USB 網卡每次重新列舉（睡眠喚醒 / 重插 / 換孔）會鑄出**新的 interface GUID**，新 GUID 一律從 AutomaticMetric 開始 → 手動 9000 形同消失
- 證據：登錄檔 `Tcpip\Parameters\Interfaces` 下同一張 USB 網卡有**兩個** GUID（`{74715fab}` 今天、`{abbd6e51}` 昨天）都掛 9000，且 Fast Startup 已關（HiberbootEnabled=0），排除快速啟動因素
- 結論：`tools/netpriority/` 的「照 GUID 寫 InterfaceMetric」持久化策略對會 GUID churn 的 USB 網卡無解；治本要改「照網卡描述（InterfaceDescription 含 Realtek USB GbE）於登入 + NetworkProfile 連線事件重設」的排程工作。已提建議，使用者本次選擇暫不採用

### 2026/06/18

#### ✅ 完成項目
- 從零做完新工具 `tools/calib_designer/`（**校正設計工具**，初版叫線性內插設計工具，後改名）：`main.py`/`app.py`/`engine.py`/`theme.py`/`manifest.json`/`make_icon.py`/`.bat`/`README.md`/`電流校正範例.csv`
- 核心 `engine.py`（純 Python 可單測）：分段線性查表(LUT) 配點演算法 **貪婪(Douglas-Peucker)** 與 **DP minimax 最佳**、均勻分點、線性回歸(OLS, 可選子集擬合)、評估、三方比較、C/CSV 匯出產生器
- 兩種模式（給點數找位置 / 給目標誤差找最少點數，相對量度時顯示「% 以內」）、兩種誤差量度（絕對 / 相對%）
- UI：tk datagrid 輸入（雙擊編輯、節點欄）、嵌入式 matplotlib（裝進系統 Python 3.12）、中文字型 fallback、可捲動控制面板
- C 匯出**完全對齊現場韌體 `linearInterpolationFromLUT`**（單組 `cal_<組名>_OV_X/TV_Y`、表內線性掃描、低於表頭由原點外插、高於表尾沿末段外插、負值箝位為 0）；另有線性回歸 `gain/offset` 匯出
- 加「校正方式」(LUT / 線性回歸)、手動插點模式、演算法說明與標準公式彈窗、圖示（.ico + launcher 用 icon.png）
- 圖表比較項目可多選疊圖（內插 演算法1/2、線性回歸、均勻、原始校正前），主方法鎖定顯示
- 逐點比較數據表改三方（原始 / 內插 / 回歸 各點誤差 + 最佳欄，僅「最佳」欄上色）
- 線性回歸取樣點數：預設=LUT 點數均勻撒點 + 滑桿調整 + 節點欄手動微調（不受 LUT 點數限制）
- 工具改名 `interp_designer` → `calib_designer`（資料夾 / manifest name / .ico / .bat 用相同英文名 / 全引用同步）；requirements 加 `matplotlib>=3.5`

#### 🐛 問題與踩坑
- datagrid inline 編輯框是原生 `tk.Entry`，沒套小數點修正 → 數字鍵盤打不進小數點；補 `bind_numpad_decimal_fix`
- C 浮點常數 bug：整數值節點用 `%g` 會產生 `0f`/`100f` 這種缺小數點的非法常數；格式化時強制補小數點
- `_interp_on_nodes` 原本假設節點含頭尾，手動取消頭尾後範圍外的點被誤算成 0、誤差爆掉 → 改成逐點比照韌體外插（原點 / 末段 / 箝位），工具誤差才跟現場一致
- 改名時 `mv` 資料夾遇到 "Device or resource busy"，根因是 Bash 持久 shell 的 cwd 卡在目標目錄內；先 `cd` 出去再 mv
- 擷取自家 tkinter 視窗驗證 UI：FindWindow 比對中文標題不穩，改用 process MainWindowHandle / EnumWindows 挑「可見且面積最小」視窗 + PrintWindow(flag 2) 抓圖

#### 📋 明日待辦
- 實機驗證：雙擊 `calib_designer.bat`、launcher 卡片是否顯示 icon、numpad 小數點實打
- 視需要把整包 `tools/calib_designer/` commit

### 2026/05/29

#### ✅ 完成項目
- 從零做完 `tools/CommBench/` host UI（對應 G071 NUCLEO 韌體）：`main.py`、`manifest.json`、`host/core/scpi_client.py`、`host/ui/{main_window,pinout_tab,i2c_tab,pmbus_tab,console_tab,log_panel}.py`
- 接線圖分頁用 tk Canvas 畫 NUCLEO-G071RB 含 CN5/CN6 Arduino header 真實 pin layout（PB8/PB9 SCL/SDA + CN6.4 3V3 + CN6.6 GND highlight、4.7k pull-up 上板外）
- COM port 自動辨識 G071：ST-Link VID `0x0483` 過濾 + `*IDN?` handshake 比對 vendor `CommBench`
- IDN 容錯比對（USB CDC 偶爾掉開頭 byte）：4 層 fallback —— 首欄完全相等 / 含 CommBench / vendor 尾段 + 第二欄含 STM32 / `Bench` + `STM32` 最寬鬆
- launcher 左側工具卡片區加 Canvas + Scrollbar、全域滑鼠滾輪 dispatch（游標位置決定捲哪個 canvas）
- Open + verify_idn 全部丟到背景 thread + `after(0, ...)` dispatch 回 UI thread，解掉「沒有回應」凍結
- I2C bus recovery 機制：`i2c_dut_bus_recover()`（HAL_I2C_DeInit → PB8/PB9 切 open-drain GPIO → toggle SCL ≤9 次 → manual STOP → HAL_I2C_Init）+ `_recover_if_stuck()` auto-wrap 4 個同步 API + SCPI `I2C1:RECOVER` / `I2C1:BUSIDLE?` + I2C tab `Recover bus` 按鈕
- PMBus 完整支援（韌體 + host）：7 個 SCPI 命令（`PMBUS:OP[?] / ONOFF[?] / STATUS? / REV? / MFRREV? / PEC[?]`）+ PMBus 分頁 bit-level 解碼（OPERATION 4 欄位 / ON_OFF_CONFIG 5 bits / STATUS_WORD 16 bits 全部對應 PMBus spec §11.1/§12.1/§12.2 文字）
- PMBus PEC（SMBus CRC-8 poly 0x07）：`crc8_smbus` + `pmbus_pec_write` / `pmbus_pec_read` helper + 7 個 handler 全部加 PEC TX/verify
- PMBus PEC 從 stateful 改 stateless：每個命令自帶 `<pec>` 最後一個 arg，UI checkbox 純本地、按下命令時即時帶到 SCPI，no global state drift
- MFRREV 兩階段讀：先讀 1 byte 拿 count，count=0/0xFF（chip 不支援）直接回 empty，否則用 exact 長度讀第二階段、避免 NACK 卡 bus
- 留下 `tools/CommBench/doctor.py` quick-sanity 工具（不開 UI 直接跑一輪 PMBus 命令並印結果）

#### 🐛 問題與踩坑
- **stm32-build-flash skill stale .hex bug（最坑）**：skill 的 fallback objcopy 只在 .hex/.bin **不存在**時跑，後續 .elf 更新後 .hex 不會重生 → flash 顯示 verified successfully 但 chip 跑的是舊代碼。SWD 直接 dump chip .text 跟 ELF disasm 比對才發現。修法：build 後手動 `rm -f *.hex *.bin` + `arm-none-eabi-objcopy` 強制重生。已寫進 memory `feedback_stm32_buildflash_stale_hex.md`
- **多 ST-Link 環境誤燒到 H7 板**：第一次 flash 沒指定 SN，CLI 撿到 Probe 0（另一片 H7）就把 G071 韌體（cortex-m0+）燒進去了。事後固定用 `sn=0667FF504857788667165423` 鎖死 G071
- USB CDC 開頭 byte 偶爾掉 → IDN 不穩定（`CommBench` 變 `ommBench` / `mmBench` / `ComBench`）→ host 端用 4 層 fallback 容錯比對
- PMBus PEC 行為從 stateful 改 stateless 的原因：稍早測試時 UI checkbox 不小心被改、韌體 `s_pmbus_pec_enabled` 變成 0 卻沒同步到 UI 顯示，trace 分析半天才發現 PEC 沒帶 → 直接拿掉 global state、每個命令自帶 bit
- I2C 對不存在 register 做 block read 會 NACK + 卡 bus；`_recover_if_stuck` 對 transient stuck 救得起來但需要短暫 wait，期間 `bus_idle=0` 是正常的
- clangd 對 CubeIDE Makefile project 沒 include path 配置，所有 driver header 顯示一堆紅字 → 既有問題（CubeIDE build 不受影響），這次新增的 PMBus 程式碼噪聲增加但無 build 影響

#### 📋 明日待辦
- 救回那片誤燒了 G071 韌體的 H7 板（SN `53FF74068678574858450267`）——燒回它原本的 H7 韌體就行
- 把 stale-hex bug 回報給 stm32-build-flash skill 維護者，或自己 fork 改 fallback 邏輯（看 timestamp 不是看存在）
- CommBench 韌體後續 Phase 2 周邊：UART DUT (USART1 PC4/PC5)、SPI DUT (PB3/4/5 + CS PB12-15)、ADC1 6ch、DAC1
- 把 `doctor.py` 改進——加 retry 機制、加更多 sanity check（例如：bus stuck 自動 recover）
