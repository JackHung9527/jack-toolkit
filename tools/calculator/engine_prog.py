"""程式設計師計算機引擎 — 整數 / 進位 / 位元運算 / 位寬。

語意仿 Windows 程式設計師模式：即時運算（無運算子優先權）、整數運算、
HEX/DEC/OCT/BIN 同步顯示。內部以「遮罩後的無號整數」儲存，DEC 以二補數解讀為有號。
與 tk 解耦，方便無頭測試。
"""

from __future__ import annotations

WIDTHS = {"BYTE": 8, "WORD": 16, "DWORD": 32, "QWORD": 64}
BASES = {"HEX": 16, "DEC": 10, "OCT": 8, "BIN": 2}

# 二元位元/算術運算子
BIN_OPS = ("+", "-", "*", "/", "mod", "and", "or", "xor", "nand", "nor", "lsh", "rsh", "rol", "ror")
OP_SYM = {
    "+": "+", "-": "−", "*": "×", "/": "÷", "mod": "mod",
    "and": "AND", "or": "OR", "xor": "XOR", "nand": "NAND", "nor": "NOR",
    "lsh": "Lsh", "rsh": "Rsh", "rol": "RoL", "ror": "RoR",
}


class ProgrammerEngine:
    def __init__(self) -> None:
        self.width = 32
        self.base = 16
        self.signed = True      # DEC 顯示與除法/取模/算術右移以二補數有號解讀
        self.value = 0          # 遮罩後的無號整數
        self.acc: int | None = None
        self.pending: str | None = None
        self.start_new = True
        self.error = False
        self.error_msg = ""
        self.expr = ""

    # ---- 遮罩 / 號數 ----
    @property
    def mask(self) -> int:
        return (1 << self.width) - 1

    def _to_signed(self, u: int) -> int:
        u &= self.mask
        if u >> (self.width - 1) & 1:
            return u - (1 << self.width)
        return u

    def _store(self, v: int) -> int:
        return v & self.mask

    # ---- 設定 ----
    def set_width(self, name: str) -> None:
        self.width = WIDTHS[name]
        self.value &= self.mask
        if self.acc is not None:
            self.acc &= self.mask

    def set_base(self, name: str) -> None:
        self.base = BASES[name]

    def set_signed(self, signed: bool) -> None:
        self.signed = signed

    # ---- 輸入 ----
    def input_digit(self, d: int) -> bool:
        """輸入一個數字（0..15）。超出目前進位則忽略並回傳 False。"""
        if self.error:
            self.clear()
        if d >= self.base:
            return False
        if self.start_new:
            self.value = self._store(d)
            self.start_new = False
        else:
            self.value = self._store(self.value * self.base + d)
        return True

    def backspace(self) -> None:
        if self.error:
            self.clear()
            return
        if self.start_new:
            return
        self.value = self._store(self.value // self.base)

    def clear(self) -> None:
        self.value = 0
        self.acc = None
        self.pending = None
        self.start_new = True
        self.error = False
        self.error_msg = ""
        self.expr = ""

    def clear_entry(self) -> None:
        if self.error:
            self.clear()
        else:
            self.value = 0
            self.start_new = False

    # ---- 運算 ----
    def _idiv(self, a: int, b: int) -> int:
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return q

    def _apply(self, op: str, a: int, b: int) -> int:
        # a, b 皆為遮罩後無號值；有號模式下以二補數解讀運算元
        if op in ("+", "-", "*", "/", "mod"):
            if self.signed:
                x, y = self._to_signed(a), self._to_signed(b)
            else:
                x, y = a, b
            if op == "+":
                return self._store(x + y)
            if op == "-":
                return self._store(x - y)
            if op == "*":
                return self._store(x * y)
            if op == "/":
                if y == 0:
                    raise ZeroDivisionError
                return self._store(self._idiv(x, y))
            if op == "mod":
                if y == 0:
                    raise ZeroDivisionError
                return self._store(x - self._idiv(x, y) * y)
        if op == "and":
            return self._store(a & b)
        if op == "or":
            return self._store(a | b)
        if op == "xor":
            return self._store(a ^ b)
        if op == "nand":
            return self._store(~(a & b))
        if op == "nor":
            return self._store(~(a | b))
        if op in ("lsh", "rsh"):
            amount = b & self.mask
            if op == "lsh":
                return 0 if amount >= self.width else self._store(a << amount)
            # rsh：有號做算術右移（保留符號），無號做邏輯右移
            if self.signed:
                sa = self._to_signed(a)
                if amount >= self.width:
                    return self._store(-1) if sa < 0 else 0
                return self._store(sa >> amount)
            if amount >= self.width:
                return 0
            return self._store(a >> amount)
        if op in ("rol", "ror"):
            amount = (b % self.width) if self.width else 0
            if amount == 0:
                return self._store(a)
            if op == "rol":
                return self._store((a << amount) | (a >> (self.width - amount)))
            return self._store((a >> amount) | (a << (self.width - amount)))
        raise ValueError(op)

    def operator(self, op: str) -> None:
        if self.error:
            return
        cur = self.value
        try:
            if self.pending is None:
                self.acc = cur
            elif not self.start_new:
                self.acc = self._apply(self.pending, self.acc or 0, cur)
        except ZeroDivisionError:
            self._set_error("無法除以零")
            return
        self.pending = op
        self.start_new = True
        self.value = self.acc if self.acc is not None else 0
        self.expr = self._fmt_for_expr(self.value) + " " + OP_SYM[op]

    def equals(self) -> None:
        if self.error:
            return
        cur = self.value
        try:
            if self.pending is not None:
                result = self._apply(self.pending, self.acc or 0, cur)
                self.pending = None
                self.acc = None
            else:
                result = cur
        except ZeroDivisionError:
            self._set_error("無法除以零")
            return
        self.value = result
        self.expr = ""
        self.start_new = True

    # ---- 一元 ----
    def negate(self) -> None:
        if self.error:
            return
        self.value = self._store((~self.value) + 1)
        self.start_new = True

    def bitwise_not(self) -> None:
        if self.error:
            return
        self.value = self._store(~self.value)
        self.start_new = True

    # ---- 錯誤 ----
    def _set_error(self, msg: str) -> None:
        self.error = True
        self.error_msg = msg
        self.value = 0
        self.acc = None
        self.pending = None
        self.start_new = True
        self.expr = ""

    # ---- 顯示 ----
    @staticmethod
    def _group(s: str, size: int) -> str:
        out = []
        while len(s) > size:
            out.insert(0, s[-size:])
            s = s[:-size]
        out.insert(0, s)
        return " ".join(out)

    def hex_str(self) -> str:
        return self._group(format(self.value & self.mask, "X"), 4)

    def dec_str(self) -> str:
        if self.signed:
            return str(self._to_signed(self.value))
        return str(self.value & self.mask)

    def oct_str(self) -> str:
        return format(self.value & self.mask, "o")

    def bin_str(self) -> str:
        s = format(self.value & self.mask, "0{}b".format(self.width))
        return self._group(s, 4)

    def in_base(self, base: int) -> str:
        if base == 16:
            return self.hex_str()
        if base == 10:
            return self.dec_str()
        if base == 8:
            return self.oct_str()
        return self.bin_str()

    def _fmt_for_expr(self, v: int) -> str:
        saved = self.value
        self.value = v
        out = self.in_base(self.base)
        self.value = saved
        return out

    @property
    def display(self) -> str:
        if self.error:
            return self.error_msg
        return self.in_base(self.base)
