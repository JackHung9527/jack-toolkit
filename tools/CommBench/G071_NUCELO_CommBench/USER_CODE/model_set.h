/*
 * model_set.h
 * 全專案可調參數集中區。修改這裡不需要改 driver 程式碼，也不需要動 main。
 *
 * 使用原則：
 *   - 所有 #define 形式的常數，集中在此檔
 *   - 同一份韌體支援多機種時，用 #ifdef MODEL_XXX 切換
 *   - driver / 應用層的程式碼一律從這裡讀參數，不要寫死數值
 *   - 修改後需 rebuild，不會有 runtime 開銷
 */

#ifndef MODEL_SET_H_
#define MODEL_SET_H_

/* ====================================================================
 * 機種選擇（同一專案多機種共用韌體時用 #ifdef 切換）
 * ==================================================================== */
#define MODEL_DEFAULT
// #define MODEL_VARIANT_A
// #define MODEL_VARIANT_B


/* ====================================================================
 * 系統時序
 * ==================================================================== */
#define MS_LOOP_TICK_PERIOD_US 100U     /* softwareTim tick = 100µs */


/* ====================================================================
 * Driver 參數（依使用到的 driver 分區塊填入）
 *
 * 各 driver scaffold skill 會在此檔對應位置插入參數區塊。
 * 區塊用以下 marker 包起來，方便日後維護：
 *
 *     === MODEL_SET_<DRIVER> BEGIN ===
 *     ... 參數 ...
 *     === MODEL_SET_<DRIVER> END ===
 * ==================================================================== */


/* === MODEL_SET_I2C_DUT BEGIN === */
#define I2C_DUT_TIMEOUT_MS     100U
#define I2C_DUT_BUS_SPEED      100000UL /* informational */
/* === MODEL_SET_I2C_DUT END === */


/* === MODEL_SET_CLI BEGIN === */
#define CLI_TX_BUF_SIZE        512U     /* TX ring buffer */
#define CLI_RX_LINE_SIZE       256U     /* RX line buffer */
#define CLI_BAUD               115200UL /* informational */
/* === MODEL_SET_CLI END === */


/* === MODEL_SET_USER BEGIN === */
/* 使用者自訂參數放這裡 */

/* === MODEL_SET_USER END === */


#endif /* MODEL_SET_H_ */
