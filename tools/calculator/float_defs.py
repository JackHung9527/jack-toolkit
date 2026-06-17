"""IEEE 754 浮點數解析（單精度 float32 / 雙精度 float64）。

提供雙向轉換：十進位數值 <-> 原始位元（hex / 二進位 sign|exponent|mantissa）。
全部用標準函式庫 struct，無第三方依賴。
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass


@dataclass
class FloatView:
    bits: int          # 原始位元（整數）
    width: int         # 32 或 64
    sign: int          # 0 / 1
    exp_raw: int       # 偏移後的指數欄位（raw）
    exp_unbiased: int  # 去偏移後的實際指數
    mantissa: int      # 尾數欄位（不含隱含位）
    stored: float      # 實際被儲存（捨入後）的數值
    category: str      # 正常 / 次正常 / 零 / 無限 / NaN

    @property
    def exp_bits(self) -> int:
        return 8 if self.width == 32 else 11

    @property
    def mant_bits(self) -> int:
        return 23 if self.width == 32 else 52

    @property
    def bias(self) -> int:
        return 127 if self.width == 32 else 1023

    def hex_str(self) -> str:
        digits = self.width // 4
        return "0x" + format(self.bits, "0{}X".format(digits))

    def bin_groups(self) -> tuple[str, str, str]:
        """回傳 (sign, exponent, mantissa) 三段二進位字串。"""
        s = format(self.sign, "01b")
        e = format(self.exp_raw, "0{}b".format(self.exp_bits))
        m = format(self.mantissa, "0{}b".format(self.mant_bits))
        return s, e, m


def _fmt_struct(width: int) -> str:
    return ">f" if width == 32 else ">d"


def _categorize(width: int, exp_raw: int, mantissa: int) -> str:
    max_exp = (1 << (8 if width == 32 else 11)) - 1
    if exp_raw == 0:
        return "零" if mantissa == 0 else "次正常 (subnormal)"
    if exp_raw == max_exp:
        return "無限 (inf)" if mantissa == 0 else "NaN"
    return "正常 (normal)"


def from_value(value: float, width: int) -> FloatView:
    """由十進位數值產生 FloatView（會依精度捨入）。"""
    packed = struct.pack(_fmt_struct(width), value)
    bits = int.from_bytes(packed, "big")
    return _decode(bits, width)


def from_bits(bits: int, width: int) -> FloatView:
    """由原始位元整數產生 FloatView。"""
    mask = (1 << width) - 1
    return _decode(bits & mask, width)


def _decode(bits: int, width: int) -> FloatView:
    exp_bits = 8 if width == 32 else 11
    mant_bits = 23 if width == 32 else 52
    bias = 127 if width == 32 else 1023
    sign = (bits >> (width - 1)) & 1
    exp_raw = (bits >> mant_bits) & ((1 << exp_bits) - 1)
    mantissa = bits & ((1 << mant_bits) - 1)
    stored = struct.unpack(_fmt_struct(width), bits.to_bytes(width // 8, "big"))[0]
    exp_unbiased = (exp_raw - bias) if exp_raw != 0 else (1 - bias)
    return FloatView(
        bits=bits, width=width, sign=sign, exp_raw=exp_raw,
        exp_unbiased=exp_unbiased, mantissa=mantissa, stored=stored,
        category=_categorize(width, exp_raw, mantissa),
    )


def stored_repr(stored: float) -> str:
    """把儲存值印成易讀字串（保留足夠位數能 round-trip）。"""
    if math.isnan(stored):
        return "NaN"
    if math.isinf(stored):
        return "+inf" if stored > 0 else "-inf"
    if stored == 0:
        return "-0.0" if math.copysign(1.0, stored) < 0 else "0.0"
    return repr(stored)
