/*
 * global_includes.h
 * 統一 include 入口。
 *   - main.c 只 include 此檔，不再個別 include 其他 USER_CODE 內的 header
 *   - driver 子資料夾的 header 一律從這裡集中匯入
 *   - extern handle 宣告在這裡（CubeMX 產生的 hxxx），driver 內部就不用各自 extern
 *
 * include 順序：
 *   1. CubeMX HAL（main.h 已經帶完整 HAL 套件）
 *   2. 標準 C 函式庫
 *   3. 全專案參數（model_set.h）
 *   4. USER_CODE 共用模組（softwareTim / userCode）
 *   5. Driver 模組（由 stm32-driver-scaffold 系列 skill 自動插入到 USER_DRIVERS marker 之間）
 */

#ifndef GLOBAL_INCLUDES_H_
#define GLOBAL_INCLUDES_H_

/* 1. HAL */
#include "main.h"

/* 2. 標準 C */
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* 3. 全專案參數 */
#include "model_set.h"

/* 4. USER_CODE 共用模組 */
#include "userCode.h"
#include "softwareTim.h"

/* 5. Driver 模組（auto-managed by stm32-driver-scaffold 系列 skill）
 *    新增 driver 時，scaffold skill 會自動在下面 marker 之間插入 #include。
 *    不要手動加 driver include 在 marker 之外，會被下次 scaffold 覆寫。
 */
/* === USER_DRIVERS BEGIN === */
#include "i2c_dut/i2c_dut.h"
#include "cli/cli.h"
#include "scpi/scpi.h"
/* === USER_DRIVERS END === */


/* 6. CubeMX HAL handle extern 宣告（auto-managed by stm32-proj-init / 後續 scaffold）
 *    main.c 內 CubeMX 產出的 HAL_HandleTypeDef hxxx; 一律在此 extern 出來，
 *    USER_CODE 內任何模組（softwareTim, userCode, driver scaffold）就不用各自 extern。
 *    新增 peripheral 時，stm32-proj-init 會自動在下面 marker 之間插入 extern。
 */
/* === USER_HANDLES BEGIN === */
extern I2C_HandleTypeDef  hi2c1;
extern UART_HandleTypeDef huart2;
extern TIM_HandleTypeDef  htim6;
/* === USER_HANDLES END === */


#endif /* GLOBAL_INCLUDES_H_ */
