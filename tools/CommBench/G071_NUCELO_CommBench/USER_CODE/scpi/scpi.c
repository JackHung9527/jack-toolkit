/*
 * scpi.c
 * CommBench SCPI command dispatcher.
 *
 * 收到 cli driver 組好的一行字串 → tokenize → 線性查命令表 → 呼叫 handler。
 * Handler 內呼叫 i2c_dut / HAL_GPIO 等執行實際動作，並用 cli_printf 回應。
 */

#include "global_includes.h"
#include <ctype.h>
#include <stdlib.h>
#include <string.h>


#define SCPI_MAX_ARGS                16U
#define SCPI_MAX_DATA_BYTES          64U
#define SCPI_I2C_ADDR_MIN            0x08U
#define SCPI_I2C_ADDR_MAX            0x77U

/* PMBus 標準命令碼（PMBus Specification Part II, Rev 1.3+） */
#define PMBUS_CMD_OPERATION          0x01U
#define PMBUS_CMD_ON_OFF_CONFIG      0x02U
#define PMBUS_CMD_STATUS_WORD        0x79U
#define PMBUS_CMD_PMBUS_REVISION     0x98U
#define PMBUS_CMD_MFR_REVISION       0x9BU
/* MFR_REVISION 是 PMBus block read：第一個 byte 是 N，後面 N bytes 是字串。
 * 我們最多讀 1 + 32 bytes，足夠覆蓋常見廠商 firmware revision 字串。 */
#define PMBUS_BLOCK_MAX_BYTES        16U   /* 大多 chip MFR_REVISION ≤ 16 byte；
                                            * 讀超過會 NACK 卡 bus，需要 recovery */

/* SMBus PEC（Packet Error Code）= CRC-8 with polynomial 0x07，init 0x00。
 * 參與 CRC 的 byte 順序：
 *   write byte:  Aw, cmd, data
 *   read  byte:  Aw, cmd, Ar, data
 *   read  word:  Aw, cmd, Ar, data_low, data_high
 *   block read:  Aw, cmd, Ar, byte_count, data[0..N-1]
 * Aw = (addr7 << 1), Ar = Aw | 1
 * 預設 PEC 開啟（多數 PMBus 規格相容 device 預設啟用），可由 host 透過
 *   PMBUS:PEC 0      → 關
 *   PMBUS:PEC 1      → 開
 *   PMBUS:PEC?       → 查
 * 來切換。
 */
static uint8_t s_pmbus_pec_enabled = 1U;


static uint8_t crc8_smbus(const uint8_t *data, uint16_t len)
{
    uint8_t crc = 0x00U;
    for (uint16_t i = 0U; i < len; i++)
    {
        crc ^= data[i];
        for (uint8_t b = 0U; b < 8U; b++)
        {
            if ((crc & 0x80U) != 0U)
            {
                crc = (uint8_t)((uint8_t)(crc << 1) ^ 0x07U);
            }
            else
            {
                crc = (uint8_t)(crc << 1);
            }
        }
    }
    return crc;
}


typedef void (*scpi_handler_t)(int argc, char **argv);

typedef struct
{
    const char       *name;
    scpi_handler_t    handler;
} scpi_cmd_t;


/* ---------------- forward decls ---------------- */

static void on_line(const char *line, uint16_t len);

static int  scpi_stricmp(const char *a, const char *b);
static bool parse_u8 (const char *s, uint8_t  *out);
static bool parse_u16(const char *s, uint16_t *out);
static int  tokenize (char *line, char **argv, int max);
static bool check_i2c_addr(uint8_t addr);

static void h_idn       (int argc, char **argv);
static void h_help      (int argc, char **argv);
static void h_led_on    (int argc, char **argv);
static void h_led_off   (int argc, char **argv);
static void h_i2c_probe (int argc, char **argv);
static void h_i2c_scan  (int argc, char **argv);
static void h_i2c_read  (int argc, char **argv);
static void h_i2c_write (int argc, char **argv);
static void h_i2c_mread (int argc, char **argv);
static void h_i2c_mwrite(int argc, char **argv);
static void h_i2c_recover(int argc, char **argv);
static void h_i2c_busidle(int argc, char **argv);
static void h_pmbus_op_q     (int argc, char **argv);
static void h_pmbus_op_w     (int argc, char **argv);
static void h_pmbus_onoff_q  (int argc, char **argv);
static void h_pmbus_onoff_w  (int argc, char **argv);
static void h_pmbus_status_q (int argc, char **argv);
static void h_pmbus_rev_q    (int argc, char **argv);
static void h_pmbus_mfrrev_q (int argc, char **argv);
static void h_pmbus_pec_q    (int argc, char **argv);
static void h_pmbus_pec_w    (int argc, char **argv);


/* ---------------- command table ---------------- */

static const scpi_cmd_t s_cmds[] =
{
    { "*IDN?",         h_idn        },
    { "HELP?",         h_help       },
    { "LED:ON",        h_led_on     },
    { "LED:OFF",       h_led_off    },
    { "I2C1:PROBE",    h_i2c_probe  },
    { "I2C1:SCAN?",    h_i2c_scan   },
    { "I2C1:READ",     h_i2c_read   },
    { "I2C1:WRITE",    h_i2c_write  },
    { "I2C1:MEMREAD",  h_i2c_mread  },
    { "I2C1:MEMWRITE", h_i2c_mwrite },
    { "I2C1:RECOVER",  h_i2c_recover},
    { "I2C1:BUSIDLE?", h_i2c_busidle},
    /* === PMBus (走 I2C1 bus) === */
    { "PMBUS:OP?",     h_pmbus_op_q     },
    { "PMBUS:OP",      h_pmbus_op_w     },
    { "PMBUS:ONOFF?",  h_pmbus_onoff_q  },
    { "PMBUS:ONOFF",   h_pmbus_onoff_w  },
    { "PMBUS:STATUS?", h_pmbus_status_q },
    { "PMBUS:REV?",    h_pmbus_rev_q    },
    { "PMBUS:MFRREV?", h_pmbus_mfrrev_q },
    { "PMBUS:PEC?",    h_pmbus_pec_q    },
    { "PMBUS:PEC",     h_pmbus_pec_w    },
};
static const uint8_t s_cmds_count = (uint8_t)(sizeof(s_cmds) / sizeof(s_cmds[0]));


/* ================ lifecycle ================ */

void scpi_init(void)
{
    cli_set_rx_line_cb(on_line);
    cli_printf("\r\nCommBench ready. Type HELP? for command list.\r\n");
}


void scpi_handle(void)
{
    /* 目前所有命令都同步處理，無需 loop hook。預留給未來 async / streaming response。 */
}


/* ================ dispatcher ================ */

/*
 * @brief  cli driver 收完整行後的 callback。
 *         line   : 不含 \r\n 終止符的 null-terminated 字串
 *         len    : line 的長度（不含結尾 NUL）
 *         context: loop()，非 ISR，可呼叫 HAL_* blocking API
 */
static void on_line(const char *line, uint16_t len)
{
    char buf[CLI_RX_LINE_SIZE];
    if (len >= (uint16_t)sizeof(buf))
    {
        len = (uint16_t)(sizeof(buf) - 1U);
    }
    memcpy(buf, line, len);
    buf[len] = '\0';

    char *argv[SCPI_MAX_ARGS];
    int argc = tokenize(buf, argv, (int)SCPI_MAX_ARGS);
    if (argc == 0)
    {
        return;
    }

    for (uint8_t i = 0; i < s_cmds_count; i++)
    {
        if (scpi_stricmp(argv[0], s_cmds[i].name) == 0)
        {
            s_cmds[i].handler(argc, argv);
            return;
        }
    }
    cli_printf("ERR unknown command: %s (try HELP?)\r\n", argv[0]);
}


/* ================ handlers ================ */

static void h_idn(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    cli_printf("CommBench,STM32G071RB,v0.1\r\n");
}


static void h_help(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    /* split into chunks under CLI_TX_BUF_SIZE/2 = 256 byte cli_printf limit */
    cli_printf("Commands:\r\n");
    cli_printf("  *IDN?                              identification\r\n");
    cli_printf("  HELP?                              this list\r\n");
    cli_printf("  LED:ON / LED:OFF                   board LED (LD4)\r\n");
    cli_printf("  I2C1:PROBE <addr>                  check ACK\r\n");
    cli_printf("  I2C1:SCAN?                         scan 0x08~0x77\r\n");
    cli_printf("  I2C1:READ <addr> <len>             raw read\r\n");
    cli_printf("  I2C1:WRITE <addr> <b0> [b1...]     raw write\r\n");
    cli_printf("  I2C1:MEMREAD <addr> <reg> <len>    register read\r\n");
    cli_printf("  I2C1:MEMWRITE <addr> <reg> <b0>... register write\r\n");
    cli_printf("  I2C1:RECOVER                       unstuck SCL/SDA (bus recovery)\r\n");
    cli_printf("  I2C1:BUSIDLE?                      report 1 if SCL+SDA both high\r\n");
    cli_printf("PMBus (over I2C1):\r\n");
    cli_printf("  PMBUS:OP?      <addr>              read OPERATION (0x01)\r\n");
    cli_printf("  PMBUS:OP       <addr> <byte>       write OPERATION\r\n");
    cli_printf("  PMBUS:ONOFF?   <addr>              read ON_OFF_CONFIG (0x02)\r\n");
    cli_printf("  PMBUS:ONOFF    <addr> <byte>       write ON_OFF_CONFIG\r\n");
    cli_printf("  PMBUS:STATUS?  <addr>              read STATUS_WORD (0x79)\r\n");
    cli_printf("  PMBUS:REV?     <addr>              read PMBUS_REVISION (0x98)\r\n");
    cli_printf("  PMBUS:MFRREV?  <addr>              read MFR_REVISION (0x9B, block)\r\n");
    cli_printf("  PMBUS:PEC?                         report PEC mode (1=on, 0=off)\r\n");
    cli_printf("  PMBUS:PEC      <0|1>               enable/disable SMBus PEC (default 1)\r\n");
    cli_printf("Numbers: 0x.. (hex) or decimal. len/bytes max 64.\r\n");
}


static void h_led_on(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    HAL_GPIO_WritePin(LD4_GPIO_Port, LD4_Pin, GPIO_PIN_SET);
    cli_printf("OK\r\n");
}


static void h_led_off(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    HAL_GPIO_WritePin(LD4_GPIO_Port, LD4_Pin, GPIO_PIN_RESET);
    cli_printf("OK\r\n");
}


static void h_i2c_probe(int argc, char **argv)
{
    if (argc != 2)
    {
        cli_printf("ERR usage: I2C1:PROBE <addr>\r\n");
        return;
    }
    uint8_t addr;
    if (!parse_u8(argv[1], &addr))
    {
        cli_printf("ERR bad addr: %s\r\n", argv[1]);
        return;
    }
    if (!check_i2c_addr(addr))
    {
        return;
    }

    HAL_StatusTypeDef st = i2c_dut_is_device_ready(addr);
    cli_printf("%s 0x%02X\r\n", (st == HAL_OK) ? "ACK" : "NACK", addr);
}


static void h_i2c_scan(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    uint8_t addrs[128];
    uint8_t n = i2c_dut_scan(addrs, (uint8_t)sizeof(addrs));
    cli_printf("found %u device(s):", (unsigned)n);
    for (uint8_t i = 0; i < n; i++)
    {
        cli_printf(" 0x%02X", addrs[i]);
    }
    cli_printf("\r\n");
}


static void h_i2c_read(int argc, char **argv)
{
    if (argc != 3)
    {
        cli_printf("ERR usage: I2C1:READ <addr> <len>\r\n");
        return;
    }
    uint8_t  addr;
    uint16_t len;
    if (!parse_u8(argv[1], &addr) || !parse_u16(argv[2], &len))
    {
        cli_printf("ERR bad number\r\n");
        return;
    }
    if (!check_i2c_addr(addr))
    {
        return;
    }
    if (len == 0U || len > SCPI_MAX_DATA_BYTES)
    {
        cli_printf("ERR len 1..%u\r\n", (unsigned)SCPI_MAX_DATA_BYTES);
        return;
    }

    uint8_t buf[SCPI_MAX_DATA_BYTES];
    HAL_StatusTypeDef st = i2c_dut_read(addr, buf, len);
    if (st != HAL_OK)
    {
        cli_printf("ERR HAL=%d\r\n", (int)st);
        return;
    }
    cli_printf("OK");
    for (uint16_t i = 0; i < len; i++)
    {
        cli_printf(" %02X", buf[i]);
    }
    cli_printf("\r\n");
}


static void h_i2c_write(int argc, char **argv)
{
    if (argc < 3)
    {
        cli_printf("ERR usage: I2C1:WRITE <addr> <b0> [b1...]\r\n");
        return;
    }
    uint8_t addr;
    if (!parse_u8(argv[1], &addr))
    {
        cli_printf("ERR bad addr\r\n");
        return;
    }
    if (!check_i2c_addr(addr))
    {
        return;
    }

    int n_bytes = argc - 2;
    if (n_bytes > (int)SCPI_MAX_DATA_BYTES)
    {
        cli_printf("ERR max %u bytes\r\n", (unsigned)SCPI_MAX_DATA_BYTES);
        return;
    }
    uint8_t buf[SCPI_MAX_DATA_BYTES];
    for (int i = 0; i < n_bytes; i++)
    {
        if (!parse_u8(argv[2 + i], &buf[i]))
        {
            cli_printf("ERR bad byte arg %d\r\n", i);
            return;
        }
    }

    HAL_StatusTypeDef st = i2c_dut_write(addr, buf, (uint16_t)n_bytes);
    if (st == HAL_OK)
    {
        cli_printf("OK\r\n");
    }
    else
    {
        cli_printf("ERR HAL=%d\r\n", (int)st);
    }
}


static void h_i2c_mread(int argc, char **argv)
{
    if (argc != 4)
    {
        cli_printf("ERR usage: I2C1:MEMREAD <addr> <reg> <len>\r\n");
        return;
    }
    uint8_t  addr;
    uint8_t  reg;
    uint16_t len;
    if (!parse_u8(argv[1], &addr) ||
        !parse_u8(argv[2], &reg)  ||
        !parse_u16(argv[3], &len))
    {
        cli_printf("ERR bad number\r\n");
        return;
    }
    if (!check_i2c_addr(addr))
    {
        return;
    }
    if (len == 0U || len > SCPI_MAX_DATA_BYTES)
    {
        cli_printf("ERR len 1..%u\r\n", (unsigned)SCPI_MAX_DATA_BYTES);
        return;
    }

    uint8_t buf[SCPI_MAX_DATA_BYTES];
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, reg, buf, len);
    if (st != HAL_OK)
    {
        cli_printf("ERR HAL=%d\r\n", (int)st);
        return;
    }
    cli_printf("OK");
    for (uint16_t i = 0; i < len; i++)
    {
        cli_printf(" %02X", buf[i]);
    }
    cli_printf("\r\n");
}


static void h_i2c_mwrite(int argc, char **argv)
{
    if (argc < 4)
    {
        cli_printf("ERR usage: I2C1:MEMWRITE <addr> <reg> <b0> [b1...]\r\n");
        return;
    }
    uint8_t addr;
    uint8_t reg;
    if (!parse_u8(argv[1], &addr) || !parse_u8(argv[2], &reg))
    {
        cli_printf("ERR bad addr/reg\r\n");
        return;
    }
    if (!check_i2c_addr(addr))
    {
        return;
    }

    int n_bytes = argc - 3;
    if (n_bytes > (int)SCPI_MAX_DATA_BYTES)
    {
        cli_printf("ERR max %u bytes\r\n", (unsigned)SCPI_MAX_DATA_BYTES);
        return;
    }
    uint8_t buf[SCPI_MAX_DATA_BYTES];
    for (int i = 0; i < n_bytes; i++)
    {
        if (!parse_u8(argv[3 + i], &buf[i]))
        {
            cli_printf("ERR bad byte arg %d\r\n", i);
            return;
        }
    }

    HAL_StatusTypeDef st = i2c_dut_write_reg(addr, reg, buf, (uint16_t)n_bytes);
    if (st == HAL_OK)
    {
        cli_printf("OK\r\n");
    }
    else
    {
        cli_printf("ERR HAL=%d\r\n", (int)st);
    }
}


static void h_i2c_recover(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    HAL_StatusTypeDef st = i2c_dut_bus_recover();
    uint8_t idle = i2c_dut_bus_idle();
    if (st == HAL_OK)
    {
        cli_printf("OK bus_idle=%u\r\n", (unsigned)idle);
    }
    else
    {
        cli_printf("ERR HAL=%d bus_idle=%u\r\n", (int)st, (unsigned)idle);
    }
}


static void h_i2c_busidle(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    cli_printf("%u\r\n", (unsigned)i2c_dut_bus_idle());
}


/* ================ PMBus handlers ================
 *
 * 所有 PMBus 命令都是 SMBus 之上的 profile，跑在 I2C1 bus 上。
 * 7-bit slave address 是參數，命令碼是 PMBus spec 寫死的。
 *
 * 慣例：
 *   - 讀 byte 命令用 HAL_I2C_Mem_Read with MEMADD_SIZE_8BIT
 *     transaction 是「START addr+W cmd RESTART addr+R data NACK STOP」
 *   - 寫 byte 同理用 Mem_Write
 *   - read word: 一樣 Mem_Read 2 bytes；PMBus 的 word 格式是 little-endian
 *     (low byte 先), 所以 word = buf[0] | (buf[1] << 8)
 *   - block read (MFR_REVISION) 一次讀 1 + N bytes，buf[0] 是 byte count
 * ================================================ */

static bool pmbus_parse_addr(int argc, char **argv, int expect_argc, uint8_t *addr_out,
                             const char *usage)
{
    /* 接受 expect_argc 或 expect_argc+1（多的那個是 optional <pec> 0/1） */
    if ((argc != expect_argc) && (argc != (expect_argc + 1)))
    {
        cli_printf("ERR usage: %s [pec]\r\n", usage);
        return false;
    }
    if (!parse_u8(argv[1], addr_out))
    {
        cli_printf("ERR bad addr: %s\r\n", argv[1]);
        return false;
    }
    if (!check_i2c_addr(*addr_out))
    {
        return false;
    }
    return true;
}


/* 解析「optional 最後一個 PEC arg」。
 *   - 若 argc 跟 expect_argc 一樣 → 用 global s_pmbus_pec_enabled 當預設
 *   - 若 argc = expect_argc + 1 → 用 argv[expect_argc] 那個 byte (0 或 1)
 * 回傳 0 或 1。
 */
static uint8_t pmbus_resolve_pec(int argc, char **argv, int expect_argc)
{
    if (argc == (expect_argc + 1))
    {
        uint8_t v;
        if (parse_u8(argv[expect_argc], &v) && (v <= 1U))
        {
            return v;
        }
    }
    return s_pmbus_pec_enabled;
}


static void pmbus_print_hal_err(HAL_StatusTypeDef st)
{
    /* 對 PMBus 命令統一錯誤格式，讓 host 端解析簡單 */
    cli_printf("ERR HAL=%d bus_idle=%u\r\n",
               (int)st, (unsigned)i2c_dut_bus_idle());
}


/* ---- PEC 計算共用 helper ---- */
/* Write byte/word PEC：CRC over [Aw, cmd, data...]
 *   addr7    : 7-bit I2C address
 *   cmd      : PMBus command byte
 *   data/len : data bytes to be transmitted
 */
static uint8_t pmbus_pec_write(uint8_t addr7, uint8_t cmd,
                               const uint8_t *data, uint16_t len)
{
    uint8_t hdr[2];
    hdr[0] = (uint8_t)(addr7 << 1);    /* Aw */
    hdr[1] = cmd;
    uint8_t crc = crc8_smbus(hdr, 2U);
    /* 接續 update（沿用 crc 中間值不重新初始化）— 用簡單做法：把整段 concat 起來 */
    uint8_t buf[2U + PMBUS_BLOCK_MAX_BYTES + 1U];
    buf[0] = hdr[0];
    buf[1] = hdr[1];
    if (len > sizeof(buf) - 2U) { len = (uint16_t)(sizeof(buf) - 2U); }
    for (uint16_t i = 0U; i < len; i++) { buf[2U + i] = data[i]; }
    (void)crc;
    return crc8_smbus(buf, (uint16_t)(2U + len));
}

/* Read byte/word/block PEC：CRC over [Aw, cmd, Ar, ...rx_payload...]
 * rx_payload 對 byte read = [data]
 *            對 word read = [data_lo, data_hi]
 *            對 block read = [count, data[0..count-1]]
 */
static uint8_t pmbus_pec_read(uint8_t addr7, uint8_t cmd,
                              const uint8_t *rx_payload, uint16_t rx_len)
{
    uint8_t buf[3U + PMBUS_BLOCK_MAX_BYTES + 1U];
    buf[0] = (uint8_t)(addr7 << 1);             /* Aw */
    buf[1] = cmd;
    buf[2] = (uint8_t)((addr7 << 1) | 1U);      /* Ar */
    if (rx_len > sizeof(buf) - 3U) { rx_len = (uint16_t)(sizeof(buf) - 3U); }
    for (uint16_t i = 0U; i < rx_len; i++) { buf[3U + i] = rx_payload[i]; }
    return crc8_smbus(buf, (uint16_t)(3U + rx_len));
}


/* ---- handlers ---- */

static void h_pmbus_op_q(int argc, char **argv)
{
    uint8_t addr;
    if (!pmbus_parse_addr(argc, argv, 2, &addr, "PMBUS:OP? <addr>")) return;
    uint8_t pec = pmbus_resolve_pec(argc, argv, 2);

    /* PEC on 時多讀 1 byte (PEC byte 接在 data 之後) */
    uint8_t buf[2] = {0, 0};
    uint16_t rd_len = pec ? 2U : 1U;
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, PMBUS_CMD_OPERATION, buf, rd_len);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    uint8_t data = buf[0];

    if (pec)
    {
        uint8_t pec_calc = pmbus_pec_read(addr, PMBUS_CMD_OPERATION, &data, 1U);
        if (buf[1] != pec_calc)
        {
            cli_printf("ERR PEC mismatch data=0x%02X rx=0x%02X calc=0x%02X\r\n",
                       (unsigned)data, (unsigned)buf[1], (unsigned)pec_calc);
            return;
        }
        cli_printf("OK 0x%02X pec=0x%02X\r\n", (unsigned)data, (unsigned)buf[1]);
    }
    else
    {
        cli_printf("OK 0x%02X\r\n", (unsigned)data);
    }
}


static void h_pmbus_op_w(int argc, char **argv)
{
    uint8_t addr, data;
    if (!pmbus_parse_addr(argc, argv, 3, &addr, "PMBUS:OP <addr> <byte>")) return;
    if (!parse_u8(argv[2], &data))
    {
        cli_printf("ERR bad byte: %s\r\n", argv[2]);
        return;
    }
    uint8_t pec_on = pmbus_resolve_pec(argc, argv, 3);

    HAL_StatusTypeDef st;
    if (pec_on)
    {
        uint8_t pec = pmbus_pec_write(addr, PMBUS_CMD_OPERATION, &data, 1U);
        uint8_t tx[2] = {data, pec};
        st = i2c_dut_write_reg(addr, PMBUS_CMD_OPERATION, tx, 2U);
    }
    else
    {
        st = i2c_dut_write_reg(addr, PMBUS_CMD_OPERATION, &data, 1U);
    }
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }
    cli_printf("OK\r\n");
}


static void h_pmbus_onoff_q(int argc, char **argv)
{
    uint8_t addr;
    if (!pmbus_parse_addr(argc, argv, 2, &addr, "PMBUS:ONOFF? <addr>")) return;
    uint8_t pec = pmbus_resolve_pec(argc, argv, 2);

    uint8_t buf[2] = {0, 0};
    uint16_t rd_len = pec ? 2U : 1U;
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, PMBUS_CMD_ON_OFF_CONFIG, buf, rd_len);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    uint8_t data = buf[0];

    if (pec)
    {
        uint8_t pec_calc = pmbus_pec_read(addr, PMBUS_CMD_ON_OFF_CONFIG, &data, 1U);
        if (buf[1] != pec_calc)
        {
            cli_printf("ERR PEC mismatch data=0x%02X rx=0x%02X calc=0x%02X\r\n",
                       (unsigned)data, (unsigned)buf[1], (unsigned)pec_calc);
            return;
        }
        cli_printf("OK 0x%02X pec=0x%02X\r\n", (unsigned)data, (unsigned)buf[1]);
    }
    else
    {
        cli_printf("OK 0x%02X\r\n", (unsigned)data);
    }
}


static void h_pmbus_onoff_w(int argc, char **argv)
{
    uint8_t addr, data;
    if (!pmbus_parse_addr(argc, argv, 3, &addr, "PMBUS:ONOFF <addr> <byte>")) return;
    if (!parse_u8(argv[2], &data))
    {
        cli_printf("ERR bad byte: %s\r\n", argv[2]);
        return;
    }
    uint8_t pec_on = pmbus_resolve_pec(argc, argv, 3);

    HAL_StatusTypeDef st;
    if (pec_on)
    {
        uint8_t pec = pmbus_pec_write(addr, PMBUS_CMD_ON_OFF_CONFIG, &data, 1U);
        uint8_t tx[2] = {data, pec};
        st = i2c_dut_write_reg(addr, PMBUS_CMD_ON_OFF_CONFIG, tx, 2U);
    }
    else
    {
        st = i2c_dut_write_reg(addr, PMBUS_CMD_ON_OFF_CONFIG, &data, 1U);
    }
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }
    cli_printf("OK\r\n");
}


static void h_pmbus_status_q(int argc, char **argv)
{
    uint8_t addr;
    if (!pmbus_parse_addr(argc, argv, 2, &addr, "PMBUS:STATUS? <addr>")) return;
    uint8_t pec = pmbus_resolve_pec(argc, argv, 2);

    uint8_t buf[3] = {0, 0, 0};
    uint16_t rd_len = pec ? 3U : 2U;
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, PMBUS_CMD_STATUS_WORD, buf, rd_len);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    /* PMBus word = little-endian：low byte 先 */
    uint16_t word = (uint16_t)buf[0] | ((uint16_t)buf[1] << 8);

    if (pec)
    {
        uint8_t payload[2] = {buf[0], buf[1]};
        uint8_t pec_calc = pmbus_pec_read(addr, PMBUS_CMD_STATUS_WORD, payload, 2U);
        if (buf[2] != pec_calc)
        {
            cli_printf("ERR PEC mismatch word=0x%04X rx=0x%02X calc=0x%02X\r\n",
                       (unsigned)word, (unsigned)buf[2], (unsigned)pec_calc);
            return;
        }
        cli_printf("OK 0x%04X pec=0x%02X\r\n", (unsigned)word, (unsigned)buf[2]);
    }
    else
    {
        cli_printf("OK 0x%04X\r\n", (unsigned)word);
    }
}


static void h_pmbus_rev_q(int argc, char **argv)
{
    uint8_t addr;
    if (!pmbus_parse_addr(argc, argv, 2, &addr, "PMBUS:REV? <addr>")) return;
    uint8_t pec = pmbus_resolve_pec(argc, argv, 2);

    uint8_t buf[2] = {0, 0};
    uint16_t rd_len = pec ? 2U : 1U;
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, PMBUS_CMD_PMBUS_REVISION, buf, rd_len);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    uint8_t data = buf[0];

    if (pec)
    {
        uint8_t pec_calc = pmbus_pec_read(addr, PMBUS_CMD_PMBUS_REVISION, &data, 1U);
        if (buf[1] != pec_calc)
        {
            cli_printf("ERR PEC mismatch data=0x%02X rx=0x%02X calc=0x%02X\r\n",
                       (unsigned)data, (unsigned)buf[1], (unsigned)pec_calc);
            return;
        }
    }
    /* PMBUS_REVISION：high nibble = Part I spec rev、low nibble = Part II spec rev */
    if (pec)
    {
        cli_printf("OK 0x%02X part1=1.%u part2=1.%u pec=0x%02X\r\n",
                   (unsigned)data,
                   (unsigned)((data >> 4) & 0x0FU), (unsigned)(data & 0x0FU),
                   (unsigned)buf[1]);
    }
    else
    {
        cli_printf("OK 0x%02X part1=1.%u part2=1.%u\r\n",
                   (unsigned)data,
                   (unsigned)((data >> 4) & 0x0FU), (unsigned)(data & 0x0FU));
    }
}


static void h_pmbus_mfrrev_q(int argc, char **argv)
{
    uint8_t addr;
    if (!pmbus_parse_addr(argc, argv, 2, &addr, "PMBUS:MFRREV? <addr>")) return;
    uint8_t pec = pmbus_resolve_pec(argc, argv, 2);

    /* PMBus block read 兩階段策略：
     *   1. 先只讀 1 byte 拿 count（不卡 bus）
     *   2. count == 0xFF 或 0 → chip 不支援 MFR_REVISION，直接回 "OK 0"
     *   3. 否則用 count 算 exact 長度 (1 + n [+ PEC byte])，再讀一次拿 data
     *
     * 為何兩階段：很多 chip 不支援 MFR_REVISION，cmd 0x9B 第一 byte 回 0xFF；
     * 若直接讀 N byte 會在 byte 3 以後被 NACK 並把 bus 卡住。
     *
     * PEC 限制：第一階段只讀 1 byte 無法驗 PEC（slave 預期 block read 格式，
     * count 後還會接 N data + PEC）。第二階段才能完整算 PEC。
     */

    /* === Stage 1: probe count === */
    uint8_t count_probe = 0;
    HAL_StatusTypeDef st = i2c_dut_read_reg(addr, PMBUS_CMD_MFR_REVISION, &count_probe, 1U);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    if ((count_probe == 0xFFU) || (count_probe == 0U))
    {
        /* chip 不支援 / 字串為空 */
        cli_printf("OK 0\r\n");
        return;
    }

    uint8_t n = count_probe;
    if (n > PMBUS_BLOCK_MAX_BYTES) { n = (uint8_t)PMBUS_BLOCK_MAX_BYTES; }

    /* === Stage 2: full read with exact length === */
    uint8_t buf[1U + PMBUS_BLOCK_MAX_BYTES + 1U] = {0};
    uint16_t rd_len = pec ? (uint16_t)(1U + n + 1U) : (uint16_t)(1U + n);
    st = i2c_dut_read_reg(addr, PMBUS_CMD_MFR_REVISION, buf, rd_len);
    if (st != HAL_OK) { pmbus_print_hal_err(st); return; }

    if (pec)
    {
        uint8_t pec_rx = buf[1U + n];
        uint8_t payload[1U + PMBUS_BLOCK_MAX_BYTES];
        payload[0] = buf[0];   /* count returned in stage 2 */
        for (uint8_t i = 0U; i < n; i++) { payload[1U + i] = buf[1U + i]; }
        uint8_t pec_calc = pmbus_pec_read(addr, PMBUS_CMD_MFR_REVISION,
                                          payload, (uint16_t)(1U + n));
        if (pec_rx != pec_calc)
        {
            cli_printf("ERR PEC mismatch count=%u rx=0x%02X calc=0x%02X\r\n",
                       (unsigned)n, (unsigned)pec_rx, (unsigned)pec_calc);
            return;
        }
    }

    /* 輸出格式：OK <count> <hex bytes...> */
    cli_printf("OK %u", (unsigned)n);
    for (uint8_t i = 0U; i < n; i++)
    {
        cli_printf(" %02X", (unsigned)buf[1U + i]);
    }
    cli_printf("\r\n");
}


static void h_pmbus_pec_q(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    cli_printf("%u\r\n", (unsigned)s_pmbus_pec_enabled);
}


static void h_pmbus_pec_w(int argc, char **argv)
{
    if (argc != 2)
    {
        cli_printf("ERR usage: PMBUS:PEC <0|1>\r\n");
        return;
    }
    uint8_t v;
    if (!parse_u8(argv[1], &v) || (v > 1U))
    {
        cli_printf("ERR bad value (expect 0 or 1): %s\r\n", argv[1]);
        return;
    }
    s_pmbus_pec_enabled = v;
    cli_printf("OK pec=%u\r\n", (unsigned)v);
}


/* ================ helpers ================ */

/*
 * @brief  ASCII case-insensitive 字串比較。
 *         a, b : null-terminated 字串
 *         回傳 0 = 相等，<0 / >0 同 strcmp 語意
 */
static int scpi_stricmp(const char *a, const char *b)
{
    while ((*a != '\0') && (*b != '\0'))
    {
        int ca = toupper((unsigned char)*a);
        int cb = toupper((unsigned char)*b);
        if (ca != cb)
        {
            return ca - cb;
        }
        a++;
        b++;
    }
    return (int)(unsigned char)*a - (int)(unsigned char)*b;
}


static bool parse_u8(const char *s, uint8_t *out)
{
    char *end;
    unsigned long v = strtoul(s, &end, 0);
    if ((end == s) || (*end != '\0'))
    {
        return false;
    }
    if (v > 0xFFUL)
    {
        return false;
    }
    *out = (uint8_t)v;
    return true;
}


static bool parse_u16(const char *s, uint16_t *out)
{
    char *end;
    unsigned long v = strtoul(s, &end, 0);
    if ((end == s) || (*end != '\0'))
    {
        return false;
    }
    if (v > 0xFFFFUL)
    {
        return false;
    }
    *out = (uint16_t)v;
    return true;
}


/*
 * @brief  把一行 (in-place 修改) 切成 argv 陣列。
 *         line : null-terminated 緩衝區，會被寫入 \0 分隔
 *         argv : 輸出指標陣列
 *         max  : argv 容量
 *         回傳 token 數量
 */
static int tokenize(char *line, char **argv, int max)
{
    int n = 0;
    char *p = line;
    while ((*p != '\0') && (n < max))
    {
        while ((*p != '\0') && isspace((unsigned char)*p))
        {
            p++;
        }
        if (*p == '\0')
        {
            break;
        }
        argv[n++] = p;
        while ((*p != '\0') && !isspace((unsigned char)*p))
        {
            p++;
        }
        if (*p != '\0')
        {
            *p++ = '\0';
        }
    }
    return n;
}


static bool check_i2c_addr(uint8_t addr)
{
    if ((addr < SCPI_I2C_ADDR_MIN) || (addr > SCPI_I2C_ADDR_MAX))
    {
        cli_printf("ERR i2c addr 0x%02X out of range 0x%02X-0x%02X\r\n",
                   addr, (unsigned)SCPI_I2C_ADDR_MIN, (unsigned)SCPI_I2C_ADDR_MAX);
        return false;
    }
    return true;
}
