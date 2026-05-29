# USER_CODE 資料夾

這個資料夾包含每個 STM32 專案都需要複製進去的共用程式碼框架，
以及所有由 driver-scaffold 系列 skill 自動建立的 driver 子模組。

---

## 檔案清單（基本框架）

| 檔案 | 說明 |
|------|------|
| `global_includes.h` | 統一 include 入口，main.c 只需引用此檔 |
| `model_set.h`       | 全專案可調參數集中區（thresholds / period / IO 極性 / driver tunables 全放這） |
| `softwareTim.c/.h`  | Software Timer 實作，基於 Basic Timer 中斷（100µs tick） |
| `userCode.c/.h`     | 使用者主程式框架（once / loop），printf 重定向 |

---

## Driver 子資料夾規範

新增 driver 時**一律**用獨立子資料夾：

```
USER_CODE/
├── global_includes.h
├── model_set.h
├── userCode.c / .h
├── softwareTim.c / .h
├── adc/                    ← driver 子資料夾
│   ├── adc.c
│   └── adc.h
├── uart/
│   ├── uart.c
│   └── uart.h
└── bms/
    ├── bms.c / .h
    ├── bms_ic.h
    └── bms_ic_oz7708.c / .h
```

引用 driver header 時用 **subfolder 前綴**：

```c
#include "adc/adc.h"
#include "bms/bms.h"
```

CubeIDE 的 Include Path **只需要加 `${workspace_loc:/{ProjectName}/USER_CODE}` 一個**，
不要為每個 driver 子資料夾各自加 include path。

---

## 三層狀態機規範（裸機 non-blocking 標準寫法）

所有 driver 一律遵守三層狀態機，避免阻塞 loop()。

### 三層定義

```c
/* 大項 — 整個 driver 在做什麼類型的工作 */
typedef enum
{
    XXX_TaskSel_TaskAwait     = 0,    /* idle，沒事做 */
    XXX_TaskSel_<RoutineA>    = 1,    /* 例如：讀感測器、發 packet */
    XXX_TaskSel_<RoutineB>    = 2
} XXX_TaskSel;

/* 小項 — 大項裡面的步驟流程 */
typedef enum
{
    XXX_FlowSel_FlowAwait     = 0,
    XXX_FlowSel_FirstFlow     = 1,    /* 必須跟第一個實際 step 同值 */
    XXX_FlowSel_<step1>       = 1,
    XXX_FlowSel_<step1_wait>  = 2,
    XXX_FlowSel_<step1_done>  = 3,
    XXX_FlowSel_<step2>       = 4,
    XXX_FlowSel_finish        = N
} XXX_FlowSel;

/* peripheral process — HAL 層的傳輸狀態（UART、I2C 等才需要）*/
typedef enum
{
    XXX_Pros_await       = 0,
    XXX_Pros_first       = 1,
    XXX_Pros_Tr          = 1,
    XXX_Pros_TrWaitCp    = 2,
    XXX_Pros_TrCp        = 3,
    XXX_Pros_Re          = 4,
    XXX_Pros_ReWaitCp    = 5,
    XXX_Pros_ReCp        = 6,
    XXX_Pros_ErrCallBack = 8,
    XXX_Pros_TimOut      = 9,
    XXX_Pros_finish      = 10
} XXX_Process;
```

### TASK 函式骨架

```c
void XXX_TASK(XXX_TaskSel *task, XXX_FlowSel *flow)
{
    switch ((int)*task)
    {
        case XXX_TaskSel_<RoutineA>:
        {
            switch ((int)*flow)
            {
                case XXX_FlowSel_FirstFlow:
                {
                    /* 啟動 */
                    *flow = XXX_FlowSel_<step1>;
                    /* don't break! 直接掉到下一個 case */
                }
                case XXX_FlowSel_<step1>:
                {
                    /* ... */
                    break;
                }
                case XXX_FlowSel_finish:
                {
                    *task = XXX_TaskSel_TaskAwait;
                    *flow = XXX_FlowSel_FlowAwait;
                    break;
                }
                default:
                    break;
            }
            break;
        }
        default:
            break;
    }
}
```

### 「FirstFlow → don't break」串接技巧

`FirstFlow` 跟第一個 step 同值，再用刻意省略 `break` 串接，可以讓「啟動」跟
「第一個 step」在一個 tick 內串連完成，避免多浪費一個 tick。

### HAL Callback 只設 process flag

```c
/* HAL ISR：只更動 process state，不做任何邏輯 */
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart == &uart_peripheral[PORT_1])
    {
        uart_proc[PORT_1] = UART_Pros_TrCp;
    }
}
```

主邏輯在下一次 task 函式被呼叫時，從 switch case 推進。
**不要在 ISR 內做任何 memcpy / 解析 / 計算**。

### Multi-port array 化

同一份 task 函式跑多個 port instance：

```c
XXX_TaskSel    xxx_taskSel[PORT_NUM];
XXX_FlowSel    xxx_flowSel[PORT_NUM];
XXX_Process    xxx_proc[PORT_NUM];

/* 在 loop() 內 */
for (uint8_t i = 0U; i < PORT_NUM; i++)
{
    XXX_TASK(&xxx_taskSel[i], &xxx_flowSel[i]);
}
```

---

## 使用方式

`stm32-proj-init` skill 會自動：
1. 將這些檔案複製到 `{ProjectRoot}/USER_CODE/` 資料夾
2. 在 .ioc 加入 Basic Timer（TIM6 → TIM7 → TIM16 → TIM17 擇一）並設 100µs reload
3. 調整 .ioc 的 Heap / Stack Size
4. 修改 main.c 插入 `#include "global_includes.h"` / `once()` / `loop()`

`stm32-driver-scaffold` 系列 skill（uart / i2c / adc / bms / power-protect / ...）
會在這個資料夾內自動建立 driver 子資料夾，並在 `global_includes.h` 的
`USER_DRIVERS` marker 之間插入 `#include`。

---

## 注意

- **不要手動修改 `global_includes.h` 的 `USER_DRIVERS` marker 區塊**，會被 scaffold 覆寫
- **不要把 `model_set.h` 內的 marker（`MODEL_SET_<DRIVER>`）區塊內容手動移到別處**，scaffold 會找不到
- 所有 driver 都遵守三層狀態機規範；不遵守的 driver 不要混進來，會破壞架構一致性
