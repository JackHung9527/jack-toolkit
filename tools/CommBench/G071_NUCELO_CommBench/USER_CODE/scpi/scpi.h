/*
 * scpi.h
 * SCPI 風格命令解析器，跑在 USART2 (ST-Link VCP) 上。
 *
 * 設計：
 *   - scpi_init() 註冊 cli_set_rx_line_cb()，每次收到完整一行 (CRLF/LF 結尾)
 *     就 tokenize 後在命令表 dispatch。
 *   - callback 在 cli_handle() 內被呼叫（loop context，非 ISR），可安全
 *     呼叫 HAL_I2C blocking API。
 *
 * 必須在 once() 內呼叫 scpi_init()。
 */

#ifndef SCPI_H_
#define SCPI_H_


void scpi_init(void);

void scpi_handle(void);


#endif /* SCPI_H_ */
