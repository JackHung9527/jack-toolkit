"""hex 字串 <-> bytes 共用工具。"""

from __future__ import annotations


def parse_hex(text: str) -> bytes:
    """解析使用者輸入的 hex 字串。

    接受以下格式（同時可混用）：
        "DE AD BE EF"
        "deadbeef"
        "0xDE 0xAD"
        "DE,AD,BE,EF"
        "DE-AD-BE-EF"
    """
    cleaned = (
        text.replace("0x", "")
            .replace("0X", "")
            .replace(",", " ")
            .replace("-", " ")
            .replace(":", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("\t", " ")
    )
    tokens = [t for t in cleaned.split(" ") if t]
    if len(tokens) == 1 and len(tokens[0]) % 2 == 0:
        # 整段沒空白的 hex 字串
        return bytes.fromhex(tokens[0])
    out = bytearray()
    for tok in tokens:
        if len(tok) == 1:
            tok = "0" + tok
        if len(tok) != 2:
            raise ValueError(f"invalid hex token: {tok}")
        out.append(int(tok, 16))
    return bytes(out)


def format_hex(data: bytes, group: int = 1, upper: bool = True) -> str:
    """把 bytes 變成 "DE AD BE EF" 樣式。"""
    if not data:
        return ""
    fmt = "{:02X}" if upper else "{:02x}"
    tokens = [fmt.format(b) for b in data]
    if group <= 1:
        return " ".join(tokens)
    chunks = [" ".join(tokens[i:i + group]) for i in range(0, len(tokens), group)]
    return "  ".join(chunks)
