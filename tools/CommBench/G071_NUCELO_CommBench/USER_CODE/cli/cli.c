/*
 * cli.c
 * 由 stm32-uart-scaffold 自動產生
 *
 * 周邊：USART2（HAL handle = huart2）
 * Baud：115200
 */

#include "global_includes.h"
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

extern UART_HandleTypeDef huart2;


/* ===== globals (state machine) ===== */
Cli_TaskSel
    g_cli_taskSel = Cli_TaskSel_TaskAwait;
Cli_FlowSel
    g_cli_flowSel = Cli_FlowSel_FlowAwait;

uint32_t
    g_cli_cmd     = _timxTick_cmd_start,
    g_cli_cnt     = 0;


/* ===== TX ring buffer ===== */
static uint8_t  s_tx_buf[CLI_TX_BUF_SIZE];
static volatile uint16_t s_tx_head = 0;       /* 寫入位置 */
static volatile uint16_t s_tx_tail = 0;       /* 讀取位置 */
static volatile uint8_t  s_tx_busy = 0;       /* HAL 正在送一個 byte 中 */
static uint8_t           s_tx_byte = 0;       /* 正在送的 byte（HAL_UART_Transmit_IT 必須吃外部 buffer） */


/* ===== RX line buffer ===== */
static char     s_rx_line[CLI_RX_LINE_SIZE];
static volatile uint16_t s_rx_len = 0;
static uint8_t  s_rx_byte = 0;                /* HAL_UART_Receive_IT 用 */
static volatile uint8_t  s_rx_line_ready = 0; /* 收完一整行 */
static volatile uint16_t s_rx_line_len = 0;
static Cli_RxLineCb s_rx_cb = NULL;


/* ===== private prototypes ===== */
static void cli_kick_tx(void);


/* ===========================================================================
 *  Public API
 * ========================================================================= */

/*
 * @brief  Driver 一次性初始化。在 main.c once() 呼叫一次。
 */
void cli_init(void)
{
    s_tx_head = s_tx_tail = 0;
    s_tx_busy = 0;

    s_rx_len = 0;
    s_rx_line_ready = 0;
    s_rx_line_len = 0;
    /* 啟動第一次 RX IT。每收到一個 byte 會呼叫 HAL_UART_RxCpltCallback */
    HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1);
}


/*
 * @brief  Driver 主要服務迴圈，由 main.c 的 loop() 反覆呼叫。
 *         在 RX 模式下會 dispatch 收完整的一行給 callback。
 */
void cli_handle(void)
{
    if (s_rx_line_ready)
    {
        if ((g_cli_taskSel == Cli_TaskSel_TaskAwait) &&
            (g_cli_flowSel == Cli_FlowSel_FlowAwait))
        {
            g_cli_taskSel = Cli_TaskSel_Service_Routine;
            g_cli_flowSel = Cli_FlowSel_RxDispatch;
        }
    }

    cli_TASK(&g_cli_taskSel, &g_cli_flowSel);
}


/*
 * @brief  把一段 byte 推進 TX ring buffer，立刻返回。
 *         若 HAL 沒在送字，啟動一次 HAL_UART_Transmit_IT；其餘交給 TxCpltCallback 接力。
 *
 * @param  data : 要送的資料
 * @param  len  : 長度
 * @return 實際寫入 ring buffer 的 byte 數（ring 滿了會少於 len）
 */
uint16_t cli_send(const uint8_t *data, uint16_t len)
{
    uint16_t written = 0;

    while (written < len)
    {
        uint16_t next_head = (uint16_t)((s_tx_head + 1U) % CLI_TX_BUF_SIZE);
        if (next_head == s_tx_tail)
        {
            /* ring full — 提前結束，呼叫端可重試 */
            break;
        }
        s_tx_buf[s_tx_head] = data[written];
        s_tx_head = next_head;
        written++;
    }

    cli_kick_tx();
    return written;
}


/*
 * @brief  printf-style 輸出，內部 vsnprintf 後呼叫 send()。
 *         輸出長度上限 = TX ring buffer 的一半（避免單次 print 撐爆 ring）。
 *
 * @param  fmt : printf 格式字串
 * @return 實際送出的 byte 數
 */
int cli_printf(const char *fmt, ...)
{
    char tmp[CLI_TX_BUF_SIZE / 2];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(tmp, sizeof(tmp), fmt, ap);
    va_end(ap);
    if (n < 0) return 0;
    if ((size_t)n >= sizeof(tmp)) n = (int)sizeof(tmp) - 1;
    return (int)cli_send((const uint8_t *)tmp, (uint16_t)n);
}


/*
 * @brief  TX ring 剩餘可寫空間（bytes）。
 */
uint16_t cli_tx_free(void)
{
    uint16_t head = s_tx_head;
    uint16_t tail = s_tx_tail;
    if (head >= tail) return (CLI_TX_BUF_SIZE - 1U) - (head - tail);
    return (tail - head) - 1U;
}


/*
 * @brief  註冊「收完一行」的 callback。
 *         line 不含結尾 '\n'/'\r'，已 null-terminated。
 *         callback 在 handle() 流程內被呼叫（非 ISR context），可安全呼叫 send()/printf。
 */
void cli_set_rx_line_cb(Cli_RxLineCb cb)
{
    s_rx_cb = cb;
}


/* ===========================================================================
 *  Three-layer state machine
 * ========================================================================= */
void cli_TASK(Cli_TaskSel *task,
                          Cli_FlowSel *flow)
{
    switch ((int)*task)
    {
        case Cli_TaskSel_Service_Routine:
        {
            switch ((int)*flow)
            {
                case Cli_FlowSel_RxDispatch:
                {
                    if (s_rx_line_ready)
                    {
                        if (s_rx_cb != NULL)
                        {
                            s_rx_cb(s_rx_line, s_rx_line_len);
                        }
                        s_rx_line_ready = 0;
                        s_rx_line_len = 0;
                    }
                    *flow = Cli_FlowSel_finish;
                    break;
                }
                case Cli_FlowSel_finish:
                {
                    *task = Cli_TaskSel_TaskAwait;
                    *flow = Cli_FlowSel_FlowAwait;
                    break;
                }
                default:
                    *task = Cli_TaskSel_TaskAwait;
                    *flow = Cli_FlowSel_FlowAwait;
                    break;
            }
            break;
        }
        default:
            break;
    }
}


/* ===========================================================================
 *  Internal: kick TX
 * ========================================================================= */
static void cli_kick_tx(void)
{
    /* 只有一邊持有 s_tx_busy 寫權；用簡單 critical section 避免和 ISR 競賽 */
    __disable_irq();
    if (!s_tx_busy && (s_tx_head != s_tx_tail))
    {
        s_tx_byte = s_tx_buf[s_tx_tail];
        s_tx_tail = (uint16_t)((s_tx_tail + 1U) % CLI_TX_BUF_SIZE);
        s_tx_busy = 1;
        __enable_irq();
        HAL_UART_Transmit_IT(&huart2, &s_tx_byte, 1);
        return;
    }
    __enable_irq();
}


/* ===========================================================================
 *  HAL callbacks
 *
 *  HAL_UART_TxCpltCallback / RxCpltCallback 是 weak symbol，整份 firmware 只能
 *  有一份實作。多個 UART driver 共存時要在 callback 內用 huart->Instance 判斷
 *  是哪一顆 UART。本檔的實作只處理 USART2，對其他 UART 不影響——
 *  其他 UART driver 的 callback 也應該做同樣的 instance 判斷。
 *
 *  ⚠️ 多 UART 專案的 callback 衝突：如果第二個 UART driver 也產生 weak callback，
 *  linker 會報 multiple definition。一般做法是把 callback 拆出去單獨一個檔，
 *  或用 HAL register-callback 機制（USE_HAL_UART_REGISTER_CALLBACKS=1）。
 *  Phase 3 後續會做 stm32-uart-callback-aggregator 整合多 UART 的情況。
 * ========================================================================= */

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART2) return;

    if (s_tx_head != s_tx_tail)
    {
        s_tx_byte = s_tx_buf[s_tx_tail];
        s_tx_tail = (uint16_t)((s_tx_tail + 1U) % CLI_TX_BUF_SIZE);
        HAL_UART_Transmit_IT(&huart2, &s_tx_byte, 1);
    }
    else
    {
        s_tx_busy = 0;
    }
}


void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART2) return;

    /* 收到一個 byte */
    if (!s_rx_line_ready)
    {
        if ((s_rx_byte == '\n') || (s_rx_byte == '\r'))
        {
            if (s_rx_len > 0)
            {
                s_rx_line[s_rx_len] = '\0';
                s_rx_line_len = s_rx_len;
                s_rx_line_ready = 1;
                s_rx_len = 0;
            }
            /* 空行（連續換行）就忽略 */
        }
        else if (s_rx_len < (uint16_t)(CLI_RX_LINE_SIZE - 1U))
        {
            s_rx_line[s_rx_len++] = (char)s_rx_byte;
        }
        else
        {
            /* line buffer overflow — 截斷成完整一行送出，避免一直積 */
            s_rx_line[s_rx_len] = '\0';
            s_rx_line_len = s_rx_len;
            s_rx_line_ready = 1;
            s_rx_len = 0;
        }
    }
    /* 不論是否成功都要再啟動下一次 RX IT */
    HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1);
}


/*
 * 重定向 stdio 的 printf。
 * arm-none-eabi-newlib 的 printf 最終會呼叫 _write；改寫它即可把標準 printf
 * 直接導到本 UART driver。
 *
 * ⚠️ 全 firmware 只能有一份 _write。若其他模組也想 retarget，必須在這一份
 * _write 內 dispatch（看 file descriptor 區分 stdout / stderr / 自訂）。
 */
__attribute__((used)) int _write(int file, char *ptr, int len)
{
    (void)file;
    return (int)cli_send((const uint8_t *)ptr, (uint16_t)len);
}
