# G071_NUCELO_CommBench — ST-Link (SWD) 燒錄工具

> 由 `stm32-stlink-flash` skill 於 2026-07-08 產生，針對「同時接 G071 + H7 兩顆 ST-Link」的環境客製。

## 這是什麼 / 怎麼用

給你**以後自己燒 G071 CommBench 韌體**用的工具，不用開 STM32CubeIDE。

**最快：** 把 ST-Link (G071 NUCLEO 的 USB) 接上電腦 → 雙擊 [flash.bat](flash.bat) → 等它印 `[DONE] G071 firmware updated` 就好。

雙擊視窗如果會自動關看不到結果，改雙擊 [flash_keepopen.bat](flash_keepopen.bat)（跑完要自己打 `exit` 才關）。

## 為什麼要這個工具而不是直接用 CubeProgrammer

你的桌機**同時接了兩顆 ST-Link**：
- `NUCLEO-G071RB`（SN `0667FF504857788667165423`）← 這是要燒的
- 另一顆 H7 板（SN `53FF74068678574858450267`）← 之前曾被誤燒過 G071 韌體

本工具用 **Board Name (`NUCLEO-G071`) 自動鎖定 G071**，並把 `sn=` 帶進每個燒錄指令，
所以**永遠只會燒到 G071，不會誤觸 H7**。找不到 G071 會直接報錯停下（exit 7），不會亂燒。

## 換新韌體時要做什麼

1. 重新編譯後，把新的 `.hex` 丟進 [hex/](hex/) 資料夾。
2. 檔名建議帶 8 碼日期（例 `CommBench_20260708.hex`）→ 工具會自動挑**日期最新**那個。
3. 舊的 hex 可留著（不會被選到）或自行刪除。

> 目前 hex/ 內已放好剛編好的版本：`CommBench_20260708.hex`

## 檔案結構

```
flash_via_stlink/
├── flash.bat            互動入口（雙擊即燒，跑完 pause）
├── flash_keepopen.bat   保險版（cmd /k，視窗不自動關）
├── program.ps1          主腳本（4 stage：選 hex → 鎖定 G071 → 燒+驗 → reset）
├── config.ini           所有可調設定（見下）
├── hex/                 放 .hex（已放最新版）
├── logs/                每次執行的 log（可 .gitignore）
└── README.md           本檔
```

## 設定 (config.ini)

| 區段 | 欄位 | 用途 |
|---|---|---|
| firmware | HEX_DIR | hex 檔資料夾（預設 `hex`） |
| programmer | CLI_PATH | STM32_Programmer_CLI 位置（預設 `AUTO` 自動掃，含 CubeIDE 內建版） |
| programmer | SWD_FREQ_KHZ | SWD 頻率（預設 4000；線長/雜訊大降到 1800） |
| programmer | RESET_MODE | `SWrst`（預設，通用）/ `HWrst`（需接 NRST 線） |
| **target** | **TARGET_BOARD** | **Board Name 子字串（預設 `NUCLEO-G071`）→ 自動鎖定 G071** |
| **target** | **TARGET_SN** | **要用序號鎖死時填（優先於 TARGET_BOARD）** |

> 一律 program + verify（不提供跳過 verify 的選項）——記取「不驗證會 silent fail 燒成空 flash」的教訓。

## 指令列旗標

```powershell
.\program.ps1 -Pause         # 跑完暫停（雙擊 .bat 已預設帶）
```

## Exit code

| Code | 意思 / 處置 |
|------|-------------|
| 0 | 全部成功 |
| 1 | 找不到任何 ST-Link → 檢查 USB 線 / ST-Link 驅動 |
| 5 | 燒錄或驗證失敗 → 查 SWD 連線 / 降 SWD_FREQ_KHZ / 重插 ST-Link USB |
| 7 | 找不到目標 G071（或接多顆同名板）→ 確認 G071 USB 插好，或改 config.ini target |
| 11 | hex/ 沒有 .hex → 放一份進去 |
| 12 | 找不到 STM32_Programmer_CLI → 確認有裝 CubeProgrammer/CubeIDE |
| 99 | PowerShell 未捕捉例外 |

## 常見問題

**Q：雙擊沒反應 / 視窗閃一下就關？**
A：改雙擊 `flash_keepopen.bat`；或看 `logs/` 內最新那份 log。

**Q：報 exit 7「找不到目標 G071」？**
A：G071 NUCLEO 的 USB 沒插好，或只接了 H7。把 G071 接上再跑。

**Q：以後只接 G071 一顆，不接 H7 了？**
A：照樣能用（Board Name 一樣命中）。真的想關掉鎖定可把 `TARGET_BOARD` 清空——但只接一顆時才安全。

**Q：SWD 頻率要調嗎？**
A：預設 4000 kHz 最穩。杜邦線很長或會掉封包再降到 1800。
