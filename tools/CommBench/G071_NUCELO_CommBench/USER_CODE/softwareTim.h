/*
 * 2024/09/04 by Jack
 * Encoding: UTF-8
 */

#ifndef INTERRUPT_C_
#define INTERRUPT_C_
 
#define SoftWareTim_peripheral htim6
 
typedef enum
{
	_timxTick_NotYet 				= 0,
	_timxTick_TimUp 				= 1
}_timxTick;
 
 
typedef enum
{
	_timxTick_cmd_await 			= 0,
	_timxTick_cmd_stop 				= 1,
	_timxTick_cmd_start				= 2,
	_timxTick_cmd_ticking			= 3
}_timxTick_cmd;
 
extern volatile uint32_t
	g_softWareTimCnt;
 
uint32_t cal_timThrough(uint32_t *Cnt);
_timxTick softWareTimTick_100us(uint32_t* cmd , uint32_t* Cnt , uint32_t Period);
 
#endif /* INTERRUPT_C_ */
