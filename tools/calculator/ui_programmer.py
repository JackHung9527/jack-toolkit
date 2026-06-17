"""程式設計師計算機分頁 UI。"""

from __future__ import annotations

import tkinter as tk

import theme
from engine_prog import ProgrammerEngine, WIDTHS

_BASE_ORDER = [("HEX", 16), ("DEC", 10), ("OCT", 8), ("BIN", 2)]
_WIDTH_ORDER = ["BYTE", "WORD", "DWORD", "QWORD"]


class ProgrammerFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.engine = ProgrammerEngine()
        self.expr_var = tk.StringVar()
        self.result_var = tk.StringVar(value="0")
        self._base_btns: dict[str, tk.Button] = {}
        self._base_vals: dict[str, tk.StringVar] = {}
        self._width_btns: dict[str, tk.Button] = {}
        self._sign_btns: dict[bool, tk.Button] = {}
        self._digit_btns: dict[int, tk.Button] = {}
        self._build()
        self._refresh()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        # 顯示
        disp = tk.Frame(self, bg=theme.DISPLAY_BG)
        disp.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 0))
        disp.columnconfigure(0, weight=1)
        tk.Label(disp, textvariable=self.expr_var, anchor="e", bg=theme.DISPLAY_BG,
                 fg=theme.EXPR_FG, font=(theme.UI, 11)).grid(row=0, column=0, sticky="ew", padx=8)
        self.result_lbl = tk.Label(disp, textvariable=self.result_var, anchor="e",
                                   bg=theme.DISPLAY_BG, fg=theme.RESULT_FG, font=(theme.MONO, 26, "bold"))
        self.result_lbl.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        # 位寬選擇
        wrow = tk.Frame(self, bg=theme.BG)
        wrow.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 0))
        for c in range(4):
            wrow.columnconfigure(c, weight=1)
        for i, w in enumerate(_WIDTH_ORDER):
            b = tk.Button(wrow, text=w, command=(lambda ww=w: self._set_width(ww)),
                          bg=theme.FN_BG, fg=theme.TOGGLE_OFF_FG, activebackground=theme.FN_HOVER,
                          activeforeground=theme.TEXT_PRIMARY, relief="flat", bd=0,
                          font=(theme.UI, 9), takefocus=0)
            b.grid(row=0, column=i, sticky="nsew", padx=1, pady=2)
            self._width_btns[w] = b

        # 有號 / 無號 切換
        srow = tk.Frame(self, bg=theme.BG)
        srow.grid(row=2, column=0, sticky="ew", padx=4, pady=(2, 0))
        for c in range(2):
            srow.columnconfigure(c, weight=1)
        for i, (flag, label) in enumerate([(True, "有號 (signed)"), (False, "無號 (unsigned)")]):
            b = tk.Button(srow, text=label, command=(lambda f=flag: self._set_signed(f)),
                          bg=theme.FN_BG, fg=theme.TOGGLE_OFF_FG, activebackground=theme.FN_HOVER,
                          activeforeground=theme.TEXT_PRIMARY, relief="flat", bd=0,
                          font=(theme.UI, 9), takefocus=0)
            b.grid(row=0, column=i, sticky="nsew", padx=1, pady=2)
            self._sign_btns[flag] = b

        # 進位表（可點選切換 active base）
        table = tk.Frame(self, bg=theme.PANEL)
        table.grid(row=3, column=0, sticky="ew", padx=4, pady=(4, 0))
        table.columnconfigure(1, weight=1)
        for i, (name, _b) in enumerate(_BASE_ORDER):
            btn = tk.Button(table, text=name, width=5, command=(lambda n=name: self._set_base(n)),
                            bg=theme.PANEL, fg=theme.ACCENT, activebackground=theme.NAV_ACTIVE_BG,
                            activeforeground=theme.TEXT_PRIMARY, relief="flat", bd=0,
                            font=(theme.UI, 9, "bold"), anchor="w", takefocus=0)
            btn.grid(row=i, column=0, sticky="nsew", padx=(6, 4), pady=1)
            var = tk.StringVar(value="0")
            tk.Label(table, textvariable=var, anchor="e", bg=theme.PANEL, fg=theme.TEXT_PRIMARY,
                     font=(theme.MONO, 11)).grid(row=i, column=1, sticky="ew", padx=(0, 8))
            self._base_btns[name] = btn
            self._base_vals[name] = var

        # 鍵盤
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=4, column=0, sticky="nsew", padx=4, pady=4)
        for c in range(6):
            pad.columnconfigure(c, weight=1, uniform="k")
        for r in range(6):
            pad.rowconfigure(r, weight=1, uniform="k")

        def op(name):
            return lambda: self._do(lambda: self.engine.operator(name))

        def hexd(v):
            return lambda: self._do(lambda: self.engine.input_digit(v))

        items = [
            ("A", 0, 0, hexd(10), "num", 10), ("B", 0, 1, hexd(11), "num", 11),
            ("C", 0, 2, hexd(12), "num", 12), ("D", 0, 3, hexd(13), "num", 13),
            ("E", 0, 4, hexd(14), "num", 14), ("F", 0, 5, hexd(15), "num", 15),
            ("Lsh", 1, 0, op("lsh"), "fn", None), ("Rsh", 1, 1, op("rsh"), "fn", None),
            ("RoL", 1, 2, op("rol"), "fn", None), ("RoR", 1, 3, op("ror"), "fn", None),
            ("AND", 1, 4, op("and"), "fn", None), ("OR", 1, 5, op("or"), "fn", None),
            ("XOR", 2, 0, op("xor"), "fn", None), ("NOT", 2, 1, lambda: self._do(self.engine.bitwise_not), "fn", None),
            ("NAND", 2, 2, op("nand"), "fn", None), ("NOR", 2, 3, op("nor"), "fn", None),
            ("mod", 2, 4, op("mod"), "fn", None), ("÷", 2, 5, op("/"), "fn", None),
            ("7", 3, 0, hexd(7), "num", 7), ("8", 3, 1, hexd(8), "num", 8), ("9", 3, 2, hexd(9), "num", 9),
            ("±", 3, 3, lambda: self._do(self.engine.negate), "num", None),
            ("CE", 3, 4, lambda: self._do(self.engine.clear_entry), "fn", None), ("×", 3, 5, op("*"), "fn", None),
            ("4", 4, 0, hexd(4), "num", 4), ("5", 4, 1, hexd(5), "num", 5), ("6", 4, 2, hexd(6), "num", 6),
            ("⌫", 4, 3, lambda: self._do(self.engine.backspace), "fn", None),
            ("AC", 4, 4, lambda: self._do(self.engine.clear), "fn", None), ("−", 4, 5, op("-"), "fn", None),
            ("1", 5, 0, hexd(1), "num", 1), ("2", 5, 1, hexd(2), "num", 2), ("3", 5, 2, hexd(3), "num", 3),
            ("0", 5, 3, hexd(0), "num", 0), ("=", 5, 4, lambda: self._do(self.engine.equals), "eq", None),
            ("+", 5, 5, op("+"), "fn", None),
        ]
        for text, r, c, cmd, kind, dval in items:
            font = (theme.UI, 14) if kind == "num" else (theme.UI, 11)
            if text == "=":
                font = (theme.UI, 16, "bold")
            b = theme.grid_button(pad, text, r, c, cmd, kind, font=font)
            if dval is not None:
                self._digit_btns[dval] = b

    # ---- 行為 ----
    def _do(self, fn) -> None:
        fn()
        self._refresh()

    def _set_base(self, name: str) -> None:
        self.engine.set_base(name)
        self._refresh()

    def _set_width(self, name: str) -> None:
        self.engine.set_width(name)
        self._refresh()

    def _set_signed(self, flag: bool) -> None:
        self.engine.set_signed(flag)
        self._refresh()

    def _refresh(self) -> None:
        eng = self.engine
        self.expr_var.set(eng.expr)
        self.result_var.set(eng.display)
        # 進位表
        active = next(n for n, b in _BASE_ORDER if b == eng.base)
        for name, b in _BASE_ORDER:
            self._base_vals[name].set("錯誤" if eng.error else eng.in_base(b))
            on = (name == active)
            self._base_btns[name].configure(bg=theme.TOGGLE_ON_BG if on else theme.PANEL,
                                            fg=theme.TOGGLE_ON_FG if on else theme.ACCENT)
        # 位寬高亮
        cur_w = next(k for k, v in WIDTHS.items() if v == eng.width)
        for w, b in self._width_btns.items():
            on = (w == cur_w)
            b.configure(bg=theme.TOGGLE_ON_BG if on else theme.FN_BG,
                        fg=theme.TOGGLE_ON_FG if on else theme.TOGGLE_OFF_FG)
        # 有號 / 無號高亮
        for flag, b in self._sign_btns.items():
            on = (flag == eng.signed)
            b.configure(bg=theme.TOGGLE_ON_BG if on else theme.FN_BG,
                        fg=theme.TOGGLE_ON_FG if on else theme.TOGGLE_OFF_FG)
        # 數字鈕依進位啟用/停用
        for val, b in self._digit_btns.items():
            b.configure(state="normal" if val < eng.base else "disabled")

    # ---- 鍵盤 ----
    def on_key(self, keysym: str, char: str) -> None:
        eng = self.engine
        done = True
        if char and char in "0123456789":
            eng.input_digit(int(char))
        elif char and char.lower() in "abcdef":
            eng.input_digit(int(char, 16))
        elif char == "+":
            eng.operator("+")
        elif char == "-":
            eng.operator("-")
        elif char == "*":
            eng.operator("*")
        elif char == "/":
            eng.operator("/")
        elif char == "&":
            eng.operator("and")
        elif char == "|":
            eng.operator("or")
        elif char == "^":
            eng.operator("xor")
        elif char == "~":
            eng.bitwise_not()
        elif char == "%":
            eng.operator("mod")
        elif keysym in ("Return", "KP_Enter") or char == "=":
            eng.equals()
        elif keysym == "BackSpace":
            eng.backspace()
        elif keysym == "Escape":
            eng.clear()
        elif keysym == "Delete":
            eng.clear_entry()
        else:
            done = False
        if done:
            self._refresh()
