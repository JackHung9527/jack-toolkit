/*
 * cli.h
 * 由 stm32-uart-scaffold 自動產生
 *
 * 周邊：USART2（HAL handle = huart2，走 ST-Link VCP）
 * Baud：115200
 *
 * IT-driven UART driver，含 TX ring buffer。
 * RX line buffer / printf retarget 由 sentinel 區塊控制是否保留。
 */

#ifndef CLI_H_
#define CLI_H_


/*
 * Task Select — 大項
 */
typedef enum
{
    Cli_TaskSel_TaskAwait        = 0,
    Cli_TaskSel_Service_Routine  = 1
} Cli_TaskSel;


/*
 * Flow Select — 小項
 */
typedef enum
{
    /* common */
    Cli_FlowSel_FlowAwait        = 0,
    Cli_FlowSel_FirstFlow        = 1,
    /* Service Routine */
    Cli_FlowSel_RxDispatch       = 1,
    Cli_FlowSel_finish           = 2
} Cli_FlowSel;


/* globals */
extern Cli_TaskSel
    g_cli_taskSel;
extern Cli_FlowSel
    g_cli_flowSel;

extern uint32_t
    g_cli_cmd,
    g_cli_cnt;


typedef void (*Cli_RxLineCb)(const char *line, uint16_t len);


/* APIs */
void cli_init(void);                                     /* once() */
void cli_handle(void);                                   /* loop() */
void cli_TASK(Cli_TaskSel *task,
                          Cli_FlowSel *flow);

uint16_t cli_send(const uint8_t *data, uint16_t len);    /* 推 TX ring，回傳實際寫入 byte 數 */
int      cli_printf(const char *fmt, ...);               /* vsnprintf + send，回傳 send 出的 byte 數 */
uint16_t cli_tx_free(void);                              /* TX ring 剩餘可寫空間 */

void cli_set_rx_line_cb(Cli_RxLineCb cb);


#endif /* CLI_H_ */
