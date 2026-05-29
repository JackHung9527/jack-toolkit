/*
 * 2024/09/03 by Jack
 * Encoding: UTF-8
 */

#include "global_includes.h"


/* 重新定向 printf() */
#ifdef __GNUC__
#define PUTCHAR_PROTOTYPE int __io_putchar(int ch)
#else
#define PUTCHAR_PROTOTYPE int fputc(int ch, FILE *f)
#endif

/*
 * ex. printf("val = %d\n",val); must add "\n" in tail
 * add uart debug port
 */
PUTCHAR_PROTOTYPE
{
	//HAL_UART_Transmit(&printf_peripheral, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
	return ch;
}


/* add in int main() */
void once(void)
{
	HAL_TIM_Base_Start_IT(&SoftWareTim_peripheral);

	/* === USER_INIT_CALLS BEGIN === */
	/* driver_init() 由 stm32-*-scaffold skill 自動插入此區塊內。
	 * 規則：cb_aggregator_init() 會被插入到區塊開頭（必須最先呼叫），
	 *       其他 driver init 依 scaffold 順序追加。 */
	i2c_dut_init();
	cli_init();
	scpi_init();
	/* === USER_INIT_CALLS END === */
}


/* add in int main() while(1) */
void loop(void)
{

	/* === USER_LOOP_CALLS BEGIN === */
	/* driver_handle() 由 stm32-*-scaffold skill 自動插入此區塊內。 */
	i2c_dut_handle();
	cli_handle();
	/* === USER_LOOP_CALLS END === */
}
