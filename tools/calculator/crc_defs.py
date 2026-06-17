"""參數化 CRC 計算（簡單版，bit-by-bit）。

用通用 CRC 模型（width / poly / init / refin / refout / xorout）涵蓋常見預設，
正確性對標各演算法的標準 check 值（輸入字串 "123456789"）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrcModel:
    name: str
    width: int      # 位元寬（8 / 16 / 32）
    poly: int       # 生成多項式（不含最高位）
    init: int       # 初始值
    refin: bool     # 輸入位元反射
    refout: bool    # 輸出反射
    xorout: int     # 結果互斥或
    note: str = ""


# 內建預設（含各自標準 check 值，供自我驗證）
MODELS: list[CrcModel] = [
    CrcModel("CRC-8", 8, 0x07, 0x00, False, False, 0x00, "poly 0x07 / init 0x00"),
    CrcModel("CRC-8/SMBus (PMBus PEC)", 8, 0x07, 0x00, False, False, 0x00,
             "SMBus / PMBus PEC，與 CRC-8 同參數"),
    CrcModel("CRC-16/CCITT-FALSE", 16, 0x1021, 0xFFFF, False, False, 0x0000,
             "poly 0x1021 / init 0xFFFF"),
    CrcModel("CRC-16/MODBUS", 16, 0x8005, 0xFFFF, True, True, 0x0000,
             "poly 0x8005 / init 0xFFFF / reflect"),
    CrcModel("CRC-32", 32, 0x04C11DB7, 0xFFFFFFFF, True, True, 0xFFFFFFFF,
             "乙太網路 / zip 標準"),
]

# 各預設對 "123456789" 的標準 check 值（單元測試與自我驗證用）
CHECK_VALUES = {
    "CRC-8": 0xF4,
    "CRC-8/SMBus (PMBus PEC)": 0xF4,
    "CRC-16/CCITT-FALSE": 0x29B1,
    "CRC-16/MODBUS": 0x4B37,
    "CRC-32": 0xCBF43926,
}


def _reflect(value: int, width: int) -> int:
    result = 0
    for _ in range(width):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def crc_compute(model: CrcModel, data: bytes) -> int:
    """以 bit-by-bit 方式計算 CRC，回傳結果整數。"""
    width = model.width
    topbit = 1 << (width - 1)
    mask = (1 << width) - 1
    reg = model.init & mask
    for byte in data:
        b = _reflect(byte, 8) if model.refin else byte
        reg ^= (b << (width - 8)) & mask
        for _ in range(8):
            if reg & topbit:
                reg = ((reg << 1) ^ model.poly) & mask
            else:
                reg = (reg << 1) & mask
    if model.refout:
        reg = _reflect(reg, width)
    return (reg ^ model.xorout) & mask


def find_model(name: str) -> CrcModel:
    for m in MODELS:
        if m.name == name:
            return m
    raise KeyError(name)


def parse_input(text: str, as_hex: bool) -> bytes:
    """把輸入字串轉成位元組。as_hex=True 解析 hex（忽略空白與 0x），否則當 UTF-8 文字。"""
    if as_hex:
        cleaned = text.replace("0x", " ").replace("0X", " ")
        cleaned = "".join(ch for ch in cleaned if not ch.isspace())
        cleaned = cleaned.replace(",", "")
        if len(cleaned) % 2 != 0:
            raise ValueError("hex 位數必須為偶數")
        return bytes.fromhex(cleaned)
    return text.encode("utf-8")
