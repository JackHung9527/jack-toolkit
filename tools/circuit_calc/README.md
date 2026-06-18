# 電路計算機 circuit_calc

電子電路常用計算工具。tkinter 桌面 GUI，純標準函式庫、無第三方依賴。
上方**下拉選單**切換計算項目，每個項目附**參考電路圖**（tk Canvas 繪製），
且**所有數值欄位都附單位下拉**，可在 Ω / mΩ / µΩ / kΩ / V / mV … 之間切換；
計算引擎內部一律換算成基本 SI 單位再運算。

## 啟動

```powershell
python main.py            # 開發用，stderr 直接看得到
.\電路計算機.bat          # 雙擊：優先 pythonw（無 console）
```

也可從 jack-toolkit launcher 啟動（本目錄含 `manifest.json`）。
快捷鍵：`Ctrl+1 … Ctrl+9` 跳到前九個項目。

## 計算項目（15 項）

| 分組 | 項目 | 內容 |
|---|---|---|
| 主要 | 分流電阻電流量測 | Shunt→OPA(G)→ADC 訊號鏈：靈敏度、滿量程電流、每 LSB 電流、指定電流的 ADC 碼與 shunt 功耗，支援雙向偏壓；含 FP130A / NCS21xR 機型預設 |
| 原始 | 分壓電阻電壓 | 正向求 Vout、反推 R1/R2（附 E24/E96 標準值與驗算） |
| 原始 | 單位換算器 | 八種物理量所有 SI 字首等值 + 工程記號 |
| 基礎 | 歐姆定律 / 功率 | V/I/R/P 任填兩格解其餘 |
| 基礎 | 串 / 並聯電阻 | 多顆串/並聯等效值 + E24 |
| 基礎 | LED 限流電阻 | R=(Vsupply−Vf)/If，含功耗與 E24 |
| 韌體 | STM32 Timer / PWM | 由目標頻率反推 PSC/ARR、CCR、解析度 |
| 韌體 | UART Baud 誤差 | USARTDIV/分頻值/實際 baud/誤差（OVER16/8） |
| 韌體 | ADC 解析度 | LSB、raw↔電壓互換 |
| 電源 | 穩壓器回授分壓 | Vout=Vref(1+R1/R2)，反推 R1/R2 + E24/E96 |
| 電源 | LDO 功耗 / 發熱 | 壓差功耗、效率、接面溫度（給 θJA） |
| 電源 | 電池續航 | 容量/負載 → 運行時間，可用比例打折 |
| 濾波 | RC / RL 濾波 | τ、截止頻率 fc、5τ 穩定時間 |
| 濾波 | LC 諧振 | f₀、ω₀ |
| 濾波 | 555 計時器 | astable 頻率/週期/ton/toff/占空比 |

電流量測機型預設（規格書 2026-06 查證）：
- **FP130A** —— 遠翔 Feeling Tech 電流檢測放大器，增益由外部電阻可調，共模/供電
  2.7~28V、CMRR 120dB、SOT23-5L，可替換 NCS213R 腳位。
- **NCS213R / 214R / 210R / 211R** —— onsemi 零漂移固定增益 50 / 100 / 200 / 500 V/V，
  共模 −0.3~26V、供電 2.2~26V。選固定增益型會自動帶入 G。

## 架構

| 檔案 | 角色 |
|---|---|
| `main.py` | 進入點、下拉選單導覽、全域 excepthook |
| `theme.py` | 配色、字型、輸入框 / 結果區工廠、數字鍵盤小數點修正 |
| `units.py` | SI 字首換算、工程記號、`ValueEntry`（數值＋單位下拉元件） |
| `engine.py` | 純計算函式（所有公式），與 UI 完全解耦 |
| `schematic.py` | tk Canvas 電路圖繪圖原語（電阻/電容/電感/LED/運放/方波…） |
| `base_frame.py` | 分頁基底 `CalcFrame`（標題 / 圖 / 輸入 / 結果 + 輸入 helper） |
| `ui_csa.py` | 分流電阻電流量測（Shunt→OPA→ADC，主分頁） |
| `ui_divider.py` / `ui_units.py` | 分壓 / 單位換算（自訂版面） |
| `ui_basic.py` / `ui_firmware.py` / `ui_power.py` / `ui_filter.py` | 四包新分頁（用 `CalcFrame`） |

新增計算分頁：在對應 `ui_*.py` 寫一個 `CalcFrame` 子類別（覆寫 `build` /
`draw_diagram` / `compute`），在 `main.py` 的 `MODES` 註冊一行即可。
新增物理量：在 `units.py` 的 `QUANTITIES` 加一筆（列入 `QUANTITY_ORDER` 才會進換算器）。
