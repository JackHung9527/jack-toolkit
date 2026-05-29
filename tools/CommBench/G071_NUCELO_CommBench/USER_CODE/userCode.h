/*
 * 2024/09/03 by Jack
 * Encoding: UTF-8
 * 2024/11/28 Modified 
 *  1. "WORD" 關鍵字會跟其他ST定義文件重複 所以改進
 *  2. uint8 等等... 不使用
 * 2025/05/12 Modified
 *  1. 不使用int short 等等... 直接使用<stdint.h> 的uint8_t 等等....
 */

#ifndef __USERCODE_H
#define __USERCODE_H

#define printf_peripheral 	huart2
#define	lobyte(x)			((uint8_t)(x & 0xFF))
#define	hibyte(x)			((uint8_t)(x >> 8))
#define debugPulse do { \
	DEBUG_GPIO_Port->BSRR	= DEBUG_Pin;\
	DEBUG_GPIO_Port->BRR	= DEBUG_Pin;\
} while (0)
#define _32bitsMCU

#ifdef _32bitsMCU
 
 /*
  * STM32 32bits MCU
  * short size:		2 byte
  * int size:		4 byte
  * long size:		4 byte
  * long long size:	8 byte
  * float size:		4 byte
  * double size:	8 byte
  */
 
typedef uint8_t		BYTE;				// 8-bit unsigned
typedef uint16_t		dBYTE;				// 16-bit unsigned(Double Bytes)
typedef uint32_t		qBYTE;				// 32-bit unsigned(Quadruple Bytes)
typedef uint64_t		oBYTE;				// 64-bit unsigned(Octuple Bytes)
 
typedef union _BYTE_VAL
{
	uint8_t Val;
	struct
	{
		uint8_t b0:1;
		uint8_t b1:1;
		uint8_t b2:1;
		uint8_t b3:1;
		uint8_t b4:1;
		uint8_t b5:1;
		uint8_t b6:1;
		uint8_t b7:1;
	} bits;
} BYTE_VAL;
 
typedef union _dBYTE_VAL
{
	uint16_t Val;
	uint8_t b[2];
	struct
	{
		uint8_t BL;
		uint8_t BH;
	} byte;
	struct
	{
		uint16_t b0:1;
		uint16_t b1:1;
		uint16_t b2:1;
		uint16_t b3:1;
		uint16_t b4:1;
		uint16_t b5:1;
		uint16_t b6:1;
		uint16_t b7:1;
		uint16_t b8:1;
		uint16_t b9:1;
		uint16_t b10:1;
		uint16_t b11:1;
		uint16_t b12:1;
		uint16_t b13:1;
		uint16_t b14:1;
		uint16_t b15:1;
	} bits;
} dBYTE_VAL;
 
typedef union _qBYTE_VAL
{
	uint32_t Val;
	float FVal;
	uint16_t db[2];
	uint8_t b[4];
	struct
	{
		uint16_t dBL;
		uint16_t dBH;
	} dbyte;
	struct
	{
		uint8_t LB;
		uint8_t HB;
		uint8_t UB;
		uint8_t MB;
	} byte;
	struct
	{
		uint32_t b0:1;
		uint32_t b1:1;
		uint32_t b2:1;
		uint32_t b3:1;
		uint32_t b4:1;
		uint32_t b5:1;
		uint32_t b6:1;
		uint32_t b7:1;
		uint32_t b8:1;
		uint32_t b9:1;
		uint32_t b10:1;
		uint32_t b11:1;
		uint32_t b12:1;
		uint32_t b13:1;
		uint32_t b14:1;
		uint32_t b15:1;
		uint32_t b16:1;
		uint32_t b17:1;
		uint32_t b18:1;
		uint32_t b19:1;
		uint32_t b20:1;
		uint32_t b21:1;
		uint32_t b22:1;
		uint32_t b23:1;
		uint32_t b24:1;
		uint32_t b25:1;
		uint32_t b26:1;
		uint32_t b27:1;
		uint32_t b28:1;
		uint32_t b29:1;
		uint32_t b30:1;
		uint32_t b31:1;
	} bits;
} qBYTE_VAL;
 
typedef union _oBYTE_VAL
{
	uint64_t Val;
	uint32_t qb[2];
	uint16_t db[4];
	uint8_t b[8];
	struct
	{
		float FL;
		float FH;
	}dfloat;
	struct
	{
		uint32_t qBL;
		uint32_t qBH;
	} qbyte;
	struct
	{
		uint8_t B0;
		uint8_t B1;
		uint8_t B2;
		uint8_t B3;
		uint8_t B4;
		uint8_t B5;
		uint8_t B6;
		uint8_t B7;
	} byte;
} oBYTE_VAL;
 /*
 typedef unsigned char		uint8;
 typedef unsigned short		uint16;
 typedef unsigned int		uint32;
 typedef unsigned long long	uint64;
 typedef char				int8;
 typedef short				int16;
 typedef int				int32;
 typedef long long			int64;
 */
#endif


void once(void);
void loop(void);

#endif
 
