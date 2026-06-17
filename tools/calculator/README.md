# 小算盤 (calculator)

仿 Windows 內建計算機的多模式 tkinter 工具，純 Python 標準函式庫，無第三方依賴。

![icon](icon.png)

## 五種模式（上方導覽列切換，或 `Ctrl+1`~`Ctrl+5`）

| 模式 | 說明 |
|---|---|
| 標準 | 四則運算，累加器即時運算語意（同 Windows 標準）；`% ¹⁄ₓ x² √x ±`、記憶體鍵 `MC MR M+ M− MS`；`Decimal` 精確運算（`0.1+0.2=0.3`）、千分位顯示 |
| 工程 | 可編輯運算式列（方向鍵 / Home / End / 滑鼠點選在游標處編輯、上下鍵叫回歷史算式），支援運算子優先權與括號；`sin cos tan ln log eˣ xʸ x² √x n! π e`、`DEG/RAD` 切換 |
| 程式 | HEX/DEC/OCT/BIN 同步顯示、可切位寬 `BYTE/WORD/DWORD/QWORD`、可切 `有號/無號`（影響 DEC 顯示與除法/取模/算術右移）；位元運算 `AND OR XOR NOT NAND NOR`、移位 `Lsh Rsh RoL RoR`、`mod`、二補數負號 |
| 浮點數 | IEEE 754 解析器：輸入十進位數值 → 顯示 float32 / float64 的 hex 與二進位（符號/指數/尾數拆解）與實際儲存值；亦可由 HEX 反解 |
| CRC | 參數化 CRC：CRC-8、CRC-8/SMBus (PMBus PEC)、CRC-16/CCITT-FALSE、CRC-16/MODBUS、CRC-32，或選「自訂」自行設定 位寬 / Poly / Init / 反射輸入輸出 / XorOut；輸入支援文字或 HEX 位元組 |

## 鍵盤操作（標準 / 工程 / 程式模式）

數字、`+ - * /`、`Enter`/`=`、`Backspace`、`Esc`(清除)、`Delete`(清除輸入) 通用。
工程模式另支援 `^`(次方)、`!`(階乘)、`( )`。
程式模式另支援 `A-F`、`& | ^ ~`(AND/OR/XOR/NOT)、`%`(mod)。
`Ctrl+1`~`Ctrl+5` 切換模式（任何模式下皆可用）。
浮點數 / CRC 模式以輸入框輸入，切過去時會自動聚焦輸入框。

## 執行方式

```powershell
python main.py          # 開發用（看得到 stderr）
小算盤.bat              # 雙擊啟動（無 console；崩潰會跳 messagebox + 寫 calculator_error.log）
python ..\..\launcher.py  # 經 jack-toolkit launcher（本目錄含 manifest.json）
```

> 釘選到工作列請改用 repo 根目錄的 [pin_launcher_to_taskbar.ps1](../../pin_launcher_to_taskbar.ps1)（釘選的是 launcher）。

## 程式結構

引擎與 UI 解耦，方便無頭測試：

| 檔案 | 說明 |
|---|---|
| `main.py` | 主視窗：模式導覽列 + 內容切換 + 全域鍵盤分派 + 視窗圖示 |
| `engine_decimal.py` | 標準模式引擎（Decimal 累加器） |
| `engine_sci.py` | 工程模式引擎（運算式 tokenizer + shunting-yard） |
| `engine_prog.py` | 程式模式引擎（整數 / 進位 / 位元運算 / 位寬） |
| `crc_defs.py` | 參數化 CRC 模型與計算 |
| `float_defs.py` | IEEE 754 解析 |
| `theme.py` | 共用配色與按鈕工廠 |
| `ui_standard.py` / `ui_scientific.py` / `ui_programmer.py` / `ui_float.py` / `ui_crc.py` | 各模式分頁 UI |
| `calculator.ico` / `icon.png` | 視窗圖示 / launcher 卡片圖示（由 repo 根的 `make_icons.py` 產生） |
| `manifest.json` | 讓 jack-toolkit launcher 自動收錄 |
| `小算盤.bat` | 雙擊啟動器（pythonw + 錯誤可見 fallback） |

圖示由 repo 根目錄的 [make_icons.py](../../make_icons.py)（搭配 [iconkit.py](../../iconkit.py)）統一產生，零第三方依賴。要改設計就改 `make_icons.py` 的 `glyph_calculator()` 再重跑 `python make_icons.py`。
