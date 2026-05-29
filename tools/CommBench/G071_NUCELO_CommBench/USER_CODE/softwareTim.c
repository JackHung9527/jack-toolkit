/*
 * 2024/09/04 by Jack
 * Encoding: UTF-8
 * 2024/12/05 Modified by Jack: CntT2++ 原本加在TIM2_IRQHandler(){ CntT2++; }  現在改使用HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
 * 2024/12/16 Modified by Jack: 修改 tim2Tick_10us() 確保時序性
 * 2025/02/12 改名叫 softwareTim.c
 * 2025/03/19 定義 g_softWareTimCnt , 定義 SoftWareTim_peripheral
 */

#include "global_includes.h"

volatile uint32_t
 	 g_softWareTimCnt 			= 0;
 
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
	if (htim == &SoftWareTim_peripheral)
	{
		g_softWareTimCnt++;
	}
}

uint32_t cal_timThrough(uint32_t *Cnt)
{
	uint32_t timeThrough = 0;
	if(*Cnt > g_softWareTimCnt)
	{
		timeThrough = (0xFFFFFFFF - *Cnt)+ g_softWareTimCnt;
	}
	else
	{
		timeThrough = g_softWareTimCnt - *Cnt;
	}
	return timeThrough;
}
 
 /*
  * tick once	: cmd = _timxTick_cmd_start -> if return _timxTick_TimUp -> cmd = _timxTick_cmd_await
  * tick continue: cmd = _timxTick_cmd_start -> if return _timxTick_TimUp -> cmd = _timxTick_cmd_start
  */
_timxTick softWareTimTick_100us(uint32_t* cmd , uint32_t* Cnt , uint32_t Period)
{
	uint32_t timeThrough = 0;
	uint8_t res = _timxTick_NotYet;
	if(*Cnt > g_softWareTimCnt)
	{
		timeThrough = (0xFFFFFFFF - *Cnt)+ g_softWareTimCnt;
	}
	else
	{
		timeThrough = g_softWareTimCnt - *Cnt;
	}
	switch ((uint8_t)*cmd)
	{
		 case _timxTick_cmd_await:
		 {
			 break;
		 }
		 case _timxTick_cmd_stop:
		 {
			 res = _timxTick_TimUp;
			 break;
		 }
		 case _timxTick_cmd_start:
		 {
			 *Cnt = g_softWareTimCnt;
			 *cmd = _timxTick_cmd_ticking;
			 break;
		 }
		 case _timxTick_cmd_ticking:
		 {
			 if(timeThrough >= Period)
			 {
				 *cmd = _timxTick_cmd_stop;
			 }
			 break;
		 }
		 default:
			 break;
	}
	return res;
}
 

