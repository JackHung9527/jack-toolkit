/*
 * i2c_dut.c
 * 由 stm32-i2c-scaffold 自動產生
 *
 * 周邊：I2C1（HAL handle = hi2c1）
 * Async transport：IT
 */

#include "global_includes.h"
#include <string.h>

extern I2C_HandleTypeDef hi2c1;

#define I2C_ADDR_SHIFT(a7)   ((uint16_t)((uint16_t)(a7) << 1))

/* Bus recovery 用的 GPIO bit-bang 半週期 — 1ms 大約 500 Hz，遠低於 100 kHz
 * I2C 規格，但對 unstuck 來說越慢越穩，slave 一定來得及反應。 */
#define I2C_RECOVER_HALF_PERIOD_MS   1U
#define I2C_RECOVER_MAX_CLOCKS       9U


/* ---------------- forward decls ---------------- */

static HAL_StatusTypeDef _recover_if_stuck(HAL_StatusTypeDef st);


/* ===== globals (state machine) ===== */
I2c_dut_TaskSel
    g_i2c_dut_taskSel = I2c_dut_TaskSel_TaskAwait;
I2c_dut_FlowSel
    g_i2c_dut_flowSel = I2c_dut_FlowSel_FlowAwait;

uint32_t
    g_i2c_dut_cmd     = _timxTick_cmd_start,
    g_i2c_dut_cnt     = 0;


/* ===========================================================================
 *  Lifecycle
 * ========================================================================= */
void i2c_dut_init(void)
{
}


void i2c_dut_handle(void)
{

    i2c_dut_TASK(&g_i2c_dut_taskSel, &g_i2c_dut_flowSel);
}


void i2c_dut_TASK(I2c_dut_TaskSel *task,
                          I2c_dut_FlowSel *flow)
{
    switch ((int)*task)
    {
        case I2c_dut_TaskSel_Service_Routine:
        {
            switch ((int)*flow)
            {
                case I2c_dut_FlowSel_finish:
                {
                    *task = I2c_dut_TaskSel_TaskAwait;
                    *flow = I2c_dut_FlowSel_FlowAwait;
                    break;
                }
                default:
                    *task = I2c_dut_TaskSel_TaskAwait;
                    *flow = I2c_dut_FlowSel_FlowAwait;
                    break;
            }
            break;
        }
        default:
            break;
    }
}


/* ===========================================================================
 *  Sync (blocking) API
 *
 *  非 OK 回來時統一走 _recover_if_stuck()：若 SCL/SDA 任一被拉 low、判定 bus
 *  卡死，自動跑 i2c_dut_bus_recover() 把周邊重置；單純 NACK（bus 還在 idle）
 *  則不做動作，避免 scan 期間每個 NACK 都觸發 recovery。
 * ========================================================================= */
HAL_StatusTypeDef i2c_dut_read(uint8_t addr7, uint8_t *buf, uint16_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Master_Receive(&hi2c1, I2C_ADDR_SHIFT(addr7),
                                                  buf, len, I2C_DUT_TIMEOUT_MS);
    return _recover_if_stuck(st);
}


HAL_StatusTypeDef i2c_dut_write(uint8_t addr7, const uint8_t *buf, uint16_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Master_Transmit(&hi2c1, I2C_ADDR_SHIFT(addr7),
                                                   (uint8_t *)buf, len, I2C_DUT_TIMEOUT_MS);
    return _recover_if_stuck(st);
}


HAL_StatusTypeDef i2c_dut_read_reg(uint8_t addr7, uint8_t reg,
                                           uint8_t *buf, uint16_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Mem_Read(&hi2c1, I2C_ADDR_SHIFT(addr7), reg,
                                            I2C_MEMADD_SIZE_8BIT, buf, len,
                                            I2C_DUT_TIMEOUT_MS);
    return _recover_if_stuck(st);
}


HAL_StatusTypeDef i2c_dut_write_reg(uint8_t addr7, uint8_t reg,
                                            const uint8_t *buf, uint16_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Mem_Write(&hi2c1, I2C_ADDR_SHIFT(addr7), reg,
                                             I2C_MEMADD_SIZE_8BIT, (uint8_t *)buf, len,
                                             I2C_DUT_TIMEOUT_MS);
    return _recover_if_stuck(st);
}


HAL_StatusTypeDef i2c_dut_is_device_ready(uint8_t addr7)
{
    /* 不做 auto-recover：scan 期間 NACK 是正常結果，bus 仍 idle，
     * recover 反而會拖慢 scan ~ N * 15 ms。
     */
    return HAL_I2C_IsDeviceReady(&hi2c1, I2C_ADDR_SHIFT(addr7),
                                 1, I2C_DUT_TIMEOUT_MS);
}


/* ===========================================================================
 *  Bus scanner
 *    掃 7-bit 位址範圍 0x08..0x77（保留位 0x00-0x07 與 0x78-0x7F 不掃）。
 *    out_addrs 最多寫入 max 個有 ACK 的位址；回傳實際 ACK 的 device 總數
 *    （可能大於 max，呼叫端可比對裁切）。
 * ========================================================================= */
uint8_t i2c_dut_scan(uint8_t *out_addrs, uint8_t max)
{
    uint8_t found = 0;
    for (uint8_t addr = 0x08U; addr <= 0x77U; addr++)
    {
        if (HAL_I2C_IsDeviceReady(&hi2c1, I2C_ADDR_SHIFT(addr),
                                  1, I2C_DUT_TIMEOUT_MS) == HAL_OK)
        {
            if ((out_addrs != NULL) && (found < max))
            {
                out_addrs[found] = addr;
            }
            found++;
        }
    }
    return found;
}


/* ===========================================================================
 *  Bus recovery
 *
 *  典型應用：前一次 transaction 因為 slave 中途 clock-stretch 過久（或自身
 *  異常）導致 master timeout、HAL_I2C_Master_* 回 HAL_ERROR，此時 SCL 或 SDA
 *  可能還被拉 low（最常見：slave 還在送 ACK 階段，把 SDA 拉 low 等下一個
 *  clock）。
 *
 *  標準 unstuck 流程（NXP UM10204 §3.1.16）：
 *      1. master 釋放 SDA
 *      2. master 在 SCL 上送最多 9 個 clock pulse
 *      3. 期間 slave 看到 clock 會把 ACK bit 推完、釋放 SDA
 *      4. master 看 SDA 變 high 就停手；最後送一個 STOP（SDA low → SCL high
 *         → SDA high）讓所有 slave 進入 idle。
 *
 *  本實作把 PB8/PB9 切回 open-drain GPIO 手動 bit-bang；最後 HAL_I2C_Init
 *  會經由 HAL_I2C_MspInit 自動把 GPIO 配回 AF6 + 啟動 I2C peripheral。
 * ========================================================================= */
uint8_t i2c_dut_bus_idle(void)
{
    return ((HAL_GPIO_ReadPin(GPIOB, I2C1_SCL_Pin) == GPIO_PIN_SET) &&
            (HAL_GPIO_ReadPin(GPIOB, I2C1_SDA_Pin) == GPIO_PIN_SET)) ? 1U : 0U;
}


HAL_StatusTypeDef i2c_dut_bus_recover(void)
{
    GPIO_InitTypeDef gpio = {0};

    /* 1. 釋放 I2C 周邊對 PB8/PB9 的擁有權 */
    HAL_I2C_DeInit(&hi2c1);

    /* 2. 把 PB8/PB9 改成 open-drain GPIO output，無內部上拉（依賴外部 4.7k） */
    __HAL_RCC_GPIOB_CLK_ENABLE();
    gpio.Pin   = I2C1_SCL_Pin | I2C1_SDA_Pin;
    gpio.Mode  = GPIO_MODE_OUTPUT_OD;
    gpio.Pull  = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &gpio);

    /* 3. 先把兩條線都釋放（open-drain 寫 1 = 高阻抗，靠 pull-up 拉 high） */
    HAL_GPIO_WritePin(GPIOB, I2C1_SCL_Pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(GPIOB, I2C1_SDA_Pin, GPIO_PIN_SET);
    HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);

    /* 4. 若 SDA 仍被 slave 拉 low，toggle SCL 最多 9 次讓 slave 把剩餘 bit 推完 */
    for (uint8_t i = 0U; i < I2C_RECOVER_MAX_CLOCKS; i++)
    {
        if (HAL_GPIO_ReadPin(GPIOB, I2C1_SDA_Pin) == GPIO_PIN_SET)
        {
            break;
        }
        HAL_GPIO_WritePin(GPIOB, I2C1_SCL_Pin, GPIO_PIN_RESET);
        HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);
        HAL_GPIO_WritePin(GPIOB, I2C1_SCL_Pin, GPIO_PIN_SET);
        HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);
    }

    /* 5. 手動產生 STOP condition：SDA low → SCL high → SDA high */
    HAL_GPIO_WritePin(GPIOB, I2C1_SDA_Pin, GPIO_PIN_RESET);
    HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);
    HAL_GPIO_WritePin(GPIOB, I2C1_SCL_Pin, GPIO_PIN_SET);
    HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);
    HAL_GPIO_WritePin(GPIOB, I2C1_SDA_Pin, GPIO_PIN_SET);
    HAL_Delay(I2C_RECOVER_HALF_PERIOD_MS);

    /* 6. 重新初始化 I2C 周邊。HAL_I2C_Init 內會呼叫 HAL_I2C_MspInit 把 PB8/PB9
     *    配回 AF6 + 啟用 I2C1 clock + 設 IRQ。hi2c1.Init.* 欄位仍保留 CubeMX
     *    產生時的設定，不需要重新填。 */
    return HAL_I2C_Init(&hi2c1);
}


/* 對任何 sync API 的回傳值套用「卡死才 recover」策略。
 *   - HAL_OK：直接回傳
 *   - 非 HAL_OK 但 bus idle（SCL/SDA 都 high）：純 NACK 或 timeout，不 recover
 *   - 非 HAL_OK 且 bus 卡住：跑 recover，原 error code 仍回傳給呼叫端
 */
static HAL_StatusTypeDef _recover_if_stuck(HAL_StatusTypeDef st)
{
    if (st == HAL_OK)
    {
        return st;
    }
    if (i2c_dut_bus_idle())
    {
        return st;
    }
    (void)i2c_dut_bus_recover();
    return st;
}
