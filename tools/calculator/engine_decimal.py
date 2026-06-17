"""標準計算機引擎 — Decimal 累加器（即時運算，無運算子優先權）。

仿 Windows 標準小算盤：按下運算子先結算前一步，= 可重複套用最後一次運算。
與 tk 解耦：呼叫方法改變狀態，再讀 .display / .expr_text / .mem_present 更新 UI。
"""

from __future__ import annotations

from decimal import Decimal, getcontext, localcontext

getcontext().prec = 50

SYM = {"+": "+", "-": "−", "*": "×", "/": "÷"}


class DecimalEngine:
    def __init__(self) -> None:
        self.entry = "0"
        self.acc: Decimal | None = None
        self.pending: str | None = None
        self.last_op: str | None = None
        self.last_operand: Decimal | None = None
        self.mem: Decimal | None = None
        self.start_new = True
        self.error = False
        self.error_msg = ""
        self.expr = ""

    # ---- 共用格式 ----
    def _cur(self) -> Decimal:
        try:
            return Decimal(self.entry)
        except Exception:
            return Decimal(0)

    @staticmethod
    def _digit_count(s: str) -> int:
        return sum(1 for ch in s if ch.isdigit())

    @staticmethod
    def _to_entry(d: Decimal) -> str:
        if not d.is_finite():
            return "0"
        if d == 0:
            return "0"
        adj = d.adjusted()
        if adj >= 16 or adj <= -16:
            s = format(d, ".15e")
            mant, exp = s.split("e")
            if "." in mant:
                mant = mant.rstrip("0").rstrip(".")
            return mant + "e" + exp
        s = format(d, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    @staticmethod
    def _group(s: str) -> str:
        if "e" in s or "E" in s:
            return s
        neg = s.startswith("-")
        if neg:
            s = s[1:]
        if "." in s:
            ip, fp = s.split(".", 1)
        else:
            ip, fp = s, None
        if len(ip) > 3:
            chunks: list[str] = []
            while len(ip) > 3:
                chunks.insert(0, ip[-3:])
                ip = ip[:-3]
            chunks.insert(0, ip)
            ip = ",".join(chunks)
        out = ip if fp is None else ip + "." + fp
        return ("-" if neg else "") + out

    def _fmt(self, d: Decimal) -> str:
        return self._group(self._to_entry(d))

    def _apply(self, op: str, a: Decimal | None, b: Decimal) -> Decimal:
        if a is None:
            a = Decimal(0)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise ZeroDivisionError
            return a / b
        raise ValueError(op)

    def _set_error(self, msg: str) -> None:
        self.error = True
        self.error_msg = msg
        self.entry = "0"
        self.acc = None
        self.pending = None
        self.last_op = None
        self.last_operand = None
        self.start_new = True
        self.expr = ""

    # ---- 輸入 ----
    def input_digit(self, d: str) -> None:
        if self.error:
            self._clear_all()
        if self.start_new:
            self.entry = d
            self.start_new = False
        elif self.entry == "0":
            self.entry = d
        else:
            if self._digit_count(self.entry) >= 16:
                return
            self.entry += d

    def input_dot(self) -> None:
        if self.error:
            self._clear_all()
        if self.start_new:
            self.entry = "0."
            self.start_new = False
        elif "." not in self.entry:
            self.entry += "."

    def negate(self) -> None:
        if self.error:
            return
        if self.entry.startswith("-"):
            self.entry = self.entry[1:]
        elif self.entry not in ("0", "0."):
            self.entry = "-" + self.entry

    def backspace(self) -> None:
        if self.error:
            self._clear_all()
            return
        if self.start_new:
            return
        sign = ""
        body = self.entry
        if body.startswith("-"):
            sign, body = "-", body[1:]
        body = body[:-1]
        if body in ("", "."):
            self.entry = "0"
        else:
            self.entry = sign + body
            if self.entry in ("-", ""):
                self.entry = "0"

    # ---- 清除 ----
    def _clear_all(self) -> None:
        self.entry = "0"
        self.acc = None
        self.pending = None
        self.last_op = None
        self.last_operand = None
        self.start_new = True
        self.error = False
        self.error_msg = ""
        self.expr = ""

    def clear_all(self) -> None:
        self._clear_all()

    def clear_entry(self) -> None:
        if self.error:
            self._clear_all()
        else:
            self.entry = "0"
            self.start_new = False

    # ---- 運算 ----
    def operator(self, op: str) -> None:
        if self.error:
            return
        cur = self._cur()
        try:
            if self.pending is None:
                self.acc = cur
            elif not self.start_new:
                self.acc = self._apply(self.pending, self.acc, cur)
        except (ArithmeticError, ZeroDivisionError):
            self._set_error("無法除以零")
            return
        self.pending = op
        self.last_op = None
        self.last_operand = None
        self.start_new = True
        self.entry = self._to_entry(self.acc if self.acc is not None else Decimal(0))
        self.expr = self._fmt(self.acc if self.acc is not None else Decimal(0)) + " " + SYM[op]

    def equals(self) -> None:
        if self.error:
            return
        cur = self._cur()
        try:
            if self.pending is not None:
                self.last_op = self.pending
                self.last_operand = cur
                result = self._apply(self.pending, self.acc, cur)
                self.pending = None
                self.acc = None
            elif self.last_op is not None:
                result = self._apply(self.last_op, cur, self.last_operand or Decimal(0))
            else:
                result = cur
        except (ArithmeticError, ZeroDivisionError):
            self._set_error("無法除以零")
            return
        self.entry = self._to_entry(result)
        self.expr = ""
        self.start_new = True

    def percent(self) -> None:
        if self.error:
            return
        cur = self._cur()
        if self.pending in ("+", "-") and self.acc is not None:
            val = self.acc * cur / Decimal(100)
        elif self.pending in ("*", "/"):
            val = cur / Decimal(100)
        else:
            val = Decimal(0)
        self.entry = self._to_entry(val)
        self.start_new = True
        self.expr = self._fmt(val) if self.pending else ""

    def square(self) -> None:
        if self.error:
            return
        cur = self._cur()
        try:
            res = cur * cur
        except ArithmeticError:
            self._set_error("溢位")
            return
        self.expr = "sqr(" + self._fmt(cur) + ")"
        self.entry = self._to_entry(res)
        self.start_new = True

    def sqrt(self) -> None:
        if self.error:
            return
        cur = self._cur()
        if cur < 0:
            self._set_error("無效的輸入")
            return
        with localcontext() as ctx:
            ctx.prec = 50
            res = cur.sqrt()
        self.expr = "√(" + self._fmt(cur) + ")"
        self.entry = self._to_entry(res)
        self.start_new = True

    def reciprocal(self) -> None:
        if self.error:
            return
        cur = self._cur()
        if cur == 0:
            self._set_error("無法除以零")
            return
        res = Decimal(1) / cur
        self.expr = "1/(" + self._fmt(cur) + ")"
        self.entry = self._to_entry(res)
        self.start_new = True

    # ---- 記憶體 ----
    def mem_clear(self) -> None:
        self.mem = None

    def mem_recall(self) -> None:
        if self.error or self.mem is None:
            return
        self.entry = self._to_entry(self.mem)
        self.start_new = True

    def mem_store(self) -> None:
        if self.error:
            return
        self.mem = self._cur()
        self.start_new = True

    def mem_add(self) -> None:
        if self.error:
            return
        self.mem = (self.mem or Decimal(0)) + self._cur()
        self.start_new = True

    def mem_sub(self) -> None:
        if self.error:
            return
        self.mem = (self.mem or Decimal(0)) - self._cur()
        self.start_new = True

    # ---- 輸出 ----
    @property
    def display(self) -> str:
        return self.error_msg if self.error else self._group(self.entry)

    @property
    def expr_text(self) -> str:
        return self.expr

    @property
    def mem_present(self) -> bool:
        return self.mem is not None
