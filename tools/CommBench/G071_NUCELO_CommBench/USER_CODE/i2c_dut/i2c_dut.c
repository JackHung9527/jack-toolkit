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

/* PE=0 之後要維持至少 3 個 APB clock 才會真的重置狀態機（RM0444 §31.4.2 "PE"）。
 * 64 MHz 下 3 cycles < 50 ns，給 16 次空迴圈是明顯足夠的保險值。 */
#define I2C_PE_TOGGLE_CYCLES         16U


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
    HAL_StatusTypeDef st;

    /* 先確保周邊不是卡死狀態（見 i2c_dut_periph_stuck 的說明）。
     * 這一步很便宜（沒卡住時只是讀兩個暫存器），不會拖慢 scan。 */
    if (i2c_dut_periph_stuck())
    {
        (void)i2c_dut_periph_reset();
    }

    st = HAL_I2C_IsDeviceReady(&hi2c1, I2C_ADDR_SHIFT(addr7),
                               1, I2C_DUT_TIMEOUT_MS);

    /* 單純 NACK（bus 仍 idle、周邊也正常）不做 recover —— 那是 scan 的正常結果，
     * 每個 NACK 都跑 bit-bang recovery 會讓整輪 scan 多花 N * 15 ms。 */
    return _recover_if_stuck(st);
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

    /* 開掃前先清掉上一輪留下的卡死狀態。
     *
     * 為什麼非做不可：把 bus 拔掉時，傳輸會在半途中斷，I2C 周邊可能把 ISR.BUSY
     * 留在 set，或讓 hi2c1.State 停在非 READY。HAL_I2C_IsDeviceReady 開頭就是
     *     if (State == READY) { if (BUSY) return HAL_BUSY; } else return HAL_BUSY;
     * ——**直接回傳且不清任何東西**。所以線插回去之後每次掃描仍然全部失敗，
     * 只有 MCU reset 才會好。這正是 2026/09/21 回報的症狀。 */
    if (i2c_dut_periph_stuck())
    {
        (void)i2c_dut_periph_reset();
    }

    for (uint8_t addr = 0x08U; addr <= 0x77U; addr++)
    {
        HAL_StatusTypeDef st = HAL_I2C_IsDeviceReady(&hi2c1, I2C_ADDR_SHIFT(addr),
                                                     1, I2C_DUT_TIMEOUT_MS);
        if (st == HAL_OK)
        {
            if ((out_addrs != NULL) && (found < max))
            {
                out_addrs[found] = addr;
            }
            found++;
            continue;
        }

        /* HAL_BUSY = 周邊卡住（不是 NACK，NACK 回的是 HAL_ERROR/HAL_TIMEOUT）。
         * 不處理的話剩下的位址會全部空轉，整輪 scan 變成無意義。 */
        if (st == HAL_BUSY)
        {
            (void)i2c_dut_periph_reset();
            /* 線真的被拉住（例如 slave 卡在 ACK）才做慢速 bit-bang unstuck */
            if (!i2c_dut_bus_idle())
            {
                (void)i2c_dut_bus_recover();
            }
        }
    }
    return found;
}


/* ===========================================================================
 *  周邊層卡死偵測與重置
 *
 *  與 i2c_dut_bus_recover() 的分工：
 *    - i2c_dut_bus_recover()  處理「線被拉住」——SDA 被 slave 卡在 low，
 *      要靠 bit-bang 送 clock 把它推完。慢（~20 ms），且要重新 Init。
 *    - i2c_dut_periph_reset() 處理「線是好的，但周邊自己卡住」——最典型的就是
 *      傳輸中途把 bus 拔掉，ISR.BUSY 留在 set。這時 bus_idle() 會回 true
 *      （線插回去後被 pull-up 拉高），舊版因此判定「不用 recover」而永遠修不好。
 *      PE toggle 只要幾十奈秒，可以放心在每次交易前檢查。
 * ========================================================================= */
uint8_t i2c_dut_periph_stuck(void)
{
    if (hi2c1.State != HAL_I2C_STATE_READY)
    {
        return 1U;
    }
    if (__HAL_I2C_GET_FLAG(&hi2c1, I2C_FLAG_BUSY) != RESET)
    {
        return 1U;
    }
    return 0U;
}


HAL_StatusTypeDef i2c_dut_periph_reset(void)
{
    volatile uint32_t i;

    /* 1. 清掉會黏住的錯誤旗標（拔線多半是 BERR / ARLO） */
    __HAL_I2C_CLEAR_FLAG(&hi2c1, I2C_FLAG_BERR | I2C_FLAG_ARLO | I2C_FLAG_OVR);

    /* 2. PE toggle：PE=0 會把 I2C 狀態機連同 ISR.BUSY 一起重置，這是唯一能在
     *    不重新 Init 的情況下清掉 BUSY 的方法。 */
    __HAL_I2C_DISABLE(&hi2c1);
    for (i = 0U; i < I2C_PE_TOGGLE_CYCLES; i++)
    {
        __NOP();
    }
    __HAL_I2C_ENABLE(&hi2c1);

    /* 3. 把 HAL 這一層的狀態也拉回 READY。
     *    Lock 一定要解 —— 若前一次呼叫是在 __HAL_LOCK 之後才失敗的，Lock 會留在
     *    LOCKED，之後每個 API 開頭的 __HAL_LOCK 都直接回 HAL_BUSY。 */
    hi2c1.ErrorCode    = HAL_I2C_ERROR_NONE;
    hi2c1.State        = HAL_I2C_STATE_READY;
    /* I2C_STATE_NONE 是 HAL .c 裡的私有巨集（外部取不到），其定義就是
     * ((uint32_t)HAL_I2C_MODE_NONE)，直接用公開的那個列舉值等價。 */
    hi2c1.PreviousState = (uint32_t)HAL_I2C_MODE_NONE;
    hi2c1.Mode         = HAL_I2C_MODE_NONE;
    __HAL_UNLOCK(&hi2c1);

    return i2c_dut_periph_stuck() ? HAL_ERROR : HAL_OK;
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

    /* 線被拉住 → 慢速 bit-bang unstuck（會重新 Init，順便清掉周邊狀態） */
    if (!i2c_dut_bus_idle())
    {
        (void)i2c_dut_bus_recover();
        return st;
    }

    /* 線是好的但周邊卡住 → 只要 PE toggle 就夠，幾十奈秒。
     *
     * 舊版到「bus idle」就 return 了，於是「傳輸中途拔線」這個情境永遠修不好：
     * 線插回去後 pull-up 把兩條線拉高 → bus_idle() = true → 判定不用 recover，
     * 但 ISR.BUSY 還卡著，之後每次交易都回 HAL_BUSY，只能靠 MCU reset。 */
    if (i2c_dut_periph_stuck())
    {
        (void)i2c_dut_periph_reset();
    }
    return st;
}
