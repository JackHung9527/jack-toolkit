/*
 * i2c_dut.h
 * 由 stm32-i2c-scaffold 自動產生
 *
 * 周邊：I2C1（HAL handle = hi2c1）
 * Bus speed：100000 Hz（informational）
 *
 * I2C master bus 抽象層：
 *   - 7-bit 位址介面（內部自動 << 1 轉 HAL 8-bit）
 *   - 同步阻塞版 read/write/read_reg/write_reg
 *   - 可選 async (IT / DMA)、queue / single-slot、raw / register 變體
 *   - 可選 bus scanner
 */

#ifndef I2C_DUT_H_
#define I2C_DUT_H_

/* 顯式 include stdint 讓 IDE / clangd 認得 uint*_t（即使沒設 include path）。
 * HAL_StatusTypeDef 仍仰賴使用端先 include "global_includes.h"（→ main.h →
 * stm32g0xx_hal.h）；clangd 看 .h 獨立時會紅字 HAL_StatusTypeDef，CubeIDE
 * Makefile build 不受影響。
 */
#include <stdint.h>


/*
 * Task Select — 大項
 */
typedef enum
{
    I2c_dut_TaskSel_TaskAwait        = 0,
    I2c_dut_TaskSel_Service_Routine  = 1
} I2c_dut_TaskSel;


/*
 * Flow Select — 小項
 */
typedef enum
{
    I2c_dut_FlowSel_FlowAwait        = 0,
    I2c_dut_FlowSel_FirstFlow        = 1,
    I2c_dut_FlowSel_AsyncDispatch    = 1,
    I2c_dut_FlowSel_finish           = 2
} I2c_dut_FlowSel;


/* globals */
extern I2c_dut_TaskSel
    g_i2c_dut_taskSel;
extern I2c_dut_FlowSel
    g_i2c_dut_flowSel;

extern uint32_t
    g_i2c_dut_cmd,
    g_i2c_dut_cnt;


/* ===== Lifecycle ===== */
void i2c_dut_init(void);                                  /* once() */
void i2c_dut_handle(void);                                /* loop() */
void i2c_dut_TASK(I2c_dut_TaskSel *task,
                          I2c_dut_FlowSel *flow);


/* ===== Sync (blocking) API — timeout = I2C_DUT_TIMEOUT_MS ===== */
HAL_StatusTypeDef i2c_dut_read     (uint8_t addr7, uint8_t       *buf, uint16_t len);
HAL_StatusTypeDef i2c_dut_write    (uint8_t addr7, const uint8_t *buf, uint16_t len);
HAL_StatusTypeDef i2c_dut_read_reg (uint8_t addr7, uint8_t reg, uint8_t       *buf, uint16_t len);
HAL_StatusTypeDef i2c_dut_write_reg(uint8_t addr7, uint8_t reg, const uint8_t *buf, uint16_t len);
HAL_StatusTypeDef i2c_dut_is_device_ready(uint8_t addr7);


uint8_t i2c_dut_scan(uint8_t *out_addrs, uint8_t max);


/* ===== Bus recovery =====
 * 對被卡住的 I2C bus（SCL/SDA 任一被 slave 拉 low）做硬體層 unstuck：
 *   1. HAL_I2C_DeInit 釋放周邊
 *   2. 把 SCL/SDA 接成 open-drain GPIO 手動 bit-bang
 *   3. 若 SDA 仍 low，toggle SCL ≤ 9 次讓 slave 釋放
 *   4. 補一個 manual STOP（SDA low → SCL high → SDA high）
 *   5. HAL_I2C_Init 重新配回 I2C 周邊（透過 MspInit 把 AF6 設回去）
 * 回傳 HAL_I2C_Init 的 status。 */
HAL_StatusTypeDef i2c_dut_bus_recover(void);

/* 檢查 SCL/SDA 是否都在 high（idle）。回傳 1 = idle，0 = 有 line 被拉 low。 */
uint8_t i2c_dut_bus_idle(void);


#endif /* I2C_DUT_H_ */
