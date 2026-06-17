"""工程計算機求值器 — 運算式 tokenize + shunting-yard（支援優先權、括號、函式）。

UI 端用可編輯輸入框持有運算式字串，按 = 時呼叫 eval_str() 求值。
三角函式依角度模式（DEG/RAD）換算。以 float + math 計算。與 tk 解耦。
"""

from __future__ import annotations

import math

_FUNCS = {
    "sin", "cos", "tan", "asin", "acos", "atan",
    "sinh", "cosh", "tanh", "ln", "log", "log2",
    "exp", "sqrt", "cbrt", "abs",
}

_PREC = {"+": 2, "-": 2, "*": 3, "/": 3, "mod": 3, "^": 4}
_RIGHT = {"^"}


class SciError(Exception):
    pass


class SciEngine:
    def __init__(self) -> None:
        self.angle = "DEG"   # DEG / RAD

    def toggle_angle(self) -> None:
        self.angle = "RAD" if self.angle == "DEG" else "DEG"

    def eval_str(self, s: str) -> str:
        """求值並回傳格式化字串；失敗時丟出例外。"""
        return self._fmt(self._eval(s))

    # ---- tokenizer ----
    def _tokenize(self, s: str) -> list:
        trans = {"×": "*", "÷": "/", "−": "-", "√": "sqrt"}
        s = "".join(trans.get(ch, ch) for ch in s)
        tokens: list = []
        i = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch.isspace():
                i += 1
                continue
            if ch.isdigit() or ch == ".":
                j = i
                while j < n and (s[j].isdigit() or s[j] == "."):
                    j += 1
                tokens.append(("num", float(s[i:j])))
                i = j
                continue
            if ch == "π":
                tokens.append(("num", math.pi))
                i += 1
                continue
            if ch.isalpha():
                j = i
                while j < n and s[j].isalpha():
                    j += 1
                word = s[i:j]
                i = j
                if word == "e":
                    tokens.append(("num", math.e))
                elif word == "mod":
                    tokens.append(("op", "mod"))
                elif word in _FUNCS:
                    tokens.append(("func", word))
                else:
                    raise SciError("unknown: " + word)
                continue
            if ch in "+-*/^":
                tokens.append(("op", ch))
                i += 1
                continue
            if ch == "(":
                tokens.append(("lp",))
                i += 1
                continue
            if ch == ")":
                tokens.append(("rp",))
                i += 1
                continue
            if ch == "!":
                tokens.append(("fact",))
                i += 1
                continue
            raise SciError("bad char: " + ch)
        return tokens

    # ---- shunting-yard -> RPN ----
    def _to_rpn(self, tokens: list) -> list:
        output: list = []
        stack: list = []
        prev = None
        for tok in tokens:
            kind = tok[0]
            if kind == "num":
                output.append(tok)
            elif kind == "func":
                stack.append(tok)
            elif kind == "fact":
                output.append(tok)
            elif kind == "op":
                op = tok[1]
                if op == "-" and (prev is None or prev in ("op", "lp", "func")):
                    stack.append(("uminus",))
                else:
                    while stack and stack[-1][0] == "op":
                        top = stack[-1][1]
                        if (_PREC[top] > _PREC[op]) or (_PREC[top] == _PREC[op] and op not in _RIGHT):
                            output.append(stack.pop())
                        else:
                            break
                    while stack and stack[-1][0] == "uminus" and op != "^":
                        output.append(stack.pop())
                    stack.append(tok)
            elif kind == "lp":
                stack.append(tok)
            elif kind == "rp":
                while stack and stack[-1][0] != "lp":
                    output.append(stack.pop())
                if not stack:
                    raise SciError("括號不對稱")
                stack.pop()
                if stack and stack[-1][0] == "func":
                    output.append(stack.pop())
                if stack and stack[-1][0] == "uminus":
                    output.append(stack.pop())
            prev = kind
        while stack:
            top = stack[-1]
            if top[0] == "lp":
                raise SciError("括號不對稱")
            output.append(stack.pop())
        return output

    # ---- RPN 求值 ----
    def _eval_rpn(self, rpn: list) -> float:
        st: list[float] = []
        for tok in rpn:
            kind = tok[0]
            if kind == "num":
                st.append(tok[1])
            elif kind == "uminus":
                st.append(-st.pop())
            elif kind == "fact":
                st.append(self._factorial(st.pop()))
            elif kind == "func":
                st.append(self._call_func(tok[1], st.pop()))
            elif kind == "op":
                b = st.pop()
                a = st.pop()
                st.append(self._binop(tok[1], a, b))
            else:
                raise SciError("bad rpn")
        if len(st) != 1:
            raise SciError("運算式不完整")
        return st[0]

    def _binop(self, op: str, a: float, b: float) -> float:
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
        if op == "mod":
            if b == 0:
                raise ZeroDivisionError
            return math.fmod(a, b)
        if op == "^":
            return math.pow(a, b)
        raise SciError(op)

    def _call_func(self, name: str, x: float) -> float:
        deg = self.angle == "DEG"
        if name == "sin":
            return math.sin(math.radians(x) if deg else x)
        if name == "cos":
            return math.cos(math.radians(x) if deg else x)
        if name == "tan":
            return math.tan(math.radians(x) if deg else x)
        if name == "asin":
            r = math.asin(x)
            return math.degrees(r) if deg else r
        if name == "acos":
            r = math.acos(x)
            return math.degrees(r) if deg else r
        if name == "atan":
            r = math.atan(x)
            return math.degrees(r) if deg else r
        if name == "sinh":
            return math.sinh(x)
        if name == "cosh":
            return math.cosh(x)
        if name == "tanh":
            return math.tanh(x)
        if name == "ln":
            return math.log(x)
        if name == "log":
            return math.log10(x)
        if name == "log2":
            return math.log2(x)
        if name == "exp":
            return math.exp(x)
        if name == "sqrt":
            return math.sqrt(x)
        if name == "cbrt":
            return math.copysign(abs(x) ** (1.0 / 3.0), x)
        if name == "abs":
            return abs(x)
        raise SciError(name)

    @staticmethod
    def _factorial(x: float) -> float:
        if x < 0:
            raise SciError("負數階乘")
        if abs(x - round(x)) < 1e-9:
            return float(math.factorial(int(round(x))))
        return math.gamma(x + 1.0)

    def _eval(self, s: str) -> float:
        return self._eval_rpn(self._to_rpn(self._tokenize(s)))

    @staticmethod
    def _fmt(x: float) -> str:
        if math.isnan(x):
            return "錯誤"
        if math.isinf(x):
            return "∞" if x > 0 else "-∞"
        if x == int(x) and abs(x) < 1e16:
            return str(int(x))
        return "{:.12g}".format(x)
