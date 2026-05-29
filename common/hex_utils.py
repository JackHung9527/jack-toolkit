"""HEX / ASCII 通用解析與格式化函式。

各子工具皆可共用，純邏輯不綁 GUI。
"""

from __future__ import annotations

import re

_SEP_PATTERN = re.compile(r"[\s,\-_:]")
_HEX_PATTERN = re.compile(r"[0-9A-Fa-f]+")


def parse_hex(text: str) -> bytes:
    """把使用者輸入的 HEX 字串轉成 bytes（寬鬆模式）。

    允許大小寫混用、`0x` 前綴、與下列分隔符號：空白、逗號、減號、底線、冒號。
    例：`01 AB 99`、`01ab99`、`0xDE 0xAD`、`DE:AD:BE:EF`。
    空字串回傳 b""；含非 HEX 字元或長度為奇數則丟 ValueError。
    """
    cleaned = text.replace("0x", "").replace("0X", "")
    cleaned = _SEP_PATTERN.sub("", cleaned)
    if not cleaned:
        return b""
    if not _HEX_PATTERN.fullmatch(cleaned):
        raise ValueError("含非 HEX 字元（合法字元 0-9 A-F a-f 與分隔）")
    if len(cleaned) % 2 != 0:
        raise ValueError("HEX 字元數須為偶數（每個 byte 兩個 hex 字元）")
    return bytes.fromhex(cleaned)


parse_hex_input = parse_hex  # alias，向後相容


def format_hex(data: bytes, group: int = 1, upper: bool = True) -> str:
    """bytes 轉成 HEX 字串。

    group=1 為 `DE AD BE EF`；group=2 為 `DEAD BEEF`；以此類推。
    """
    if not data:
        return ""
    fmt = "{:02X}" if upper else "{:02x}"
    tokens = [fmt.format(b) for b in data]
    if group <= 1:
        return " ".join(tokens)
    chunks = [" ".join(tokens[i:i + group]) for i in range(0, len(tokens), group)]
    return "  ".join(chunks)


def bytes_to_hex(data: bytes) -> str:
    """bytes 轉成空白分隔大寫 HEX 字串。等同 format_hex(data, 1, True)。"""
    return format_hex(data, group=1, upper=True)


def bytes_to_ascii(data: bytes) -> str:
    """bytes 轉成可讀 ASCII。

    CR / LF / TAB 顯示為 `\\r` / `\\n`（加實際換行）/ `\\t`，
    其餘不可列印 byte 顯示為 `\\xNN`。
    """
    out: list[str] = []
    for b in data:
        if b == 0x0D:
            out.append("\\r")
        elif b == 0x0A:
            out.append("\\n\n")
        elif b == 0x09:
            out.append("\\t")
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02X}")
    return "".join(out)


def bytes_to_ascii_inline(data: bytes) -> str:
    """bytes 轉成可讀 ASCII（單行版，不會插入真正的換行）。

    CR / LF / TAB 一律顯示為跳脫 `\\r` / `\\n` / `\\t`，
    其餘不可列印 byte 顯示為 `\\xNN`。
    適合「一個封包一行」的顯示模式。
    """
    return "".join(text for text, _is_esc in bytes_to_ascii_inline_segments(data))


def bytes_to_ascii_inline_segments(data: bytes) -> list[tuple[str, bool]]:
    """跟 bytes_to_ascii_inline 同樣的渲染，但回傳 (片段文字, 是否為跳脫) tuple list。

    consumer 可拿這個結果在 GUI 上幫「跳脫字元」上色，避免使用者把資料裡
    的字面 `\\` + `r`（兩個 byte 0x5C 0x72）跟我們幫 CR (0x0D) 產出的
    `\\r` 兩個字混淆。
    連續同類型的片段會自動合併以減少 widget tag 數量。
    """
    out: list[tuple[str, bool]] = []
    buf: list[str] = []
    buf_esc = False
    for b in data:
        if b == 0x0D:
            tok, esc = "\\r", True
        elif b == 0x0A:
            tok, esc = "\\n", True
        elif b == 0x09:
            tok, esc = "\\t", True
        elif 32 <= b < 127:
            tok, esc = chr(b), False
        else:
            tok, esc = f"\\x{b:02X}", True
        if buf and esc != buf_esc:
            out.append(("".join(buf), buf_esc))
            buf = []
        buf.append(tok)
        buf_esc = esc
    if buf:
        out.append(("".join(buf), buf_esc))
    return out


def make_hex_dump_line(offset: int, chunk: bytes, bytes_per_line: int = 16) -> str:
    """產生一行 hex dump（offset + hex + ASCII），格式同 `hexdump -C`。"""
    hex_part = " ".join(f"{b:02X}" for b in chunk).ljust(bytes_per_line * 3 - 1)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    return f"{offset:08X}  {hex_part}  |{ascii_part}|"
