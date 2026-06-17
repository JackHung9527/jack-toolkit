"""標準計算機分頁 UI。"""

from __future__ import annotations

import tkinter as tk

import theme
from engine_decimal import DecimalEngine


class StandardFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.engine = DecimalEngine()
        self.expr_var = tk.StringVar()
        self.result_var = tk.StringVar(value="0")
        self._build()
        self._refresh()

    # ---- UI ----
    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        disp = tk.Frame(self, bg=theme.DISPLAY_BG)
        disp.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 0))
        disp.columnconfigure(0, weight=1)
        tk.Label(disp, textvariable=self.expr_var, anchor="e", bg=theme.DISPLAY_BG,
                 fg=theme.EXPR_FG, font=(theme.UI, 11)).grid(row=0, column=0, sticky="ew", padx=8)
        self.result_lbl = tk.Label(disp, textvariable=self.result_var, anchor="e",
                                    bg=theme.DISPLAY_BG, fg=theme.RESULT_FG, font=(theme.UI, 32, "bold"))
        self.result_lbl.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

        mem = tk.Frame(self, bg=theme.BG)
        mem.grid(row=1, column=0, sticky="nsew", padx=4)
        for c in range(5):
            mem.columnconfigure(c, weight=1)
        self._mc = self._mem_btn(mem, "MC", 0, self.engine.mem_clear)
        self._mr = self._mem_btn(mem, "MR", 1, self.engine.mem_recall)
        self._mem_btn(mem, "M+", 2, self.engine.mem_add)
        self._mem_btn(mem, "M−", 3, self.engine.mem_sub)
        self._mem_btn(mem, "MS", 4, self.engine.mem_store)

        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        for c in range(4):
            pad.columnconfigure(c, weight=1, uniform="k")
        for r in range(6):
            pad.rowconfigure(r, weight=1, uniform="k")

        layout = [
            ("%", 0, 0, "fn", self.engine.percent),
            ("CE", 0, 1, "fn", self.engine.clear_entry),
            ("C", 0, 2, "fn", self.engine.clear_all),
            ("⌫", 0, 3, "fn", self.engine.backspace),
            ("¹⁄ₓ", 1, 0, "fn", self.engine.reciprocal),
            ("x²", 1, 1, "fn", self.engine.square),
            ("√x", 1, 2, "fn", self.engine.sqrt),
            ("÷", 1, 3, "fn", lambda: self.engine.operator("/")),
            ("7", 2, 0, "num", lambda: self.engine.input_digit("7")),
            ("8", 2, 1, "num", lambda: self.engine.input_digit("8")),
            ("9", 2, 2, "num", lambda: self.engine.input_digit("9")),
            ("×", 2, 3, "fn", lambda: self.engine.operator("*")),
            ("4", 3, 0, "num", lambda: self.engine.input_digit("4")),
            ("5", 3, 1, "num", lambda: self.engine.input_digit("5")),
            ("6", 3, 2, "num", lambda: self.engine.input_digit("6")),
            ("−", 3, 3, "fn", lambda: self.engine.operator("-")),
            ("1", 4, 0, "num", lambda: self.engine.input_digit("1")),
            ("2", 4, 1, "num", lambda: self.engine.input_digit("2")),
            ("3", 4, 2, "num", lambda: self.engine.input_digit("3")),
            ("+", 4, 3, "fn", lambda: self.engine.operator("+")),
            ("±", 5, 0, "num", self.engine.negate),
            ("0", 5, 1, "num", lambda: self.engine.input_digit("0")),
            (".", 5, 2, "num", self.engine.input_dot),
            ("=", 5, 3, "eq", self.engine.equals),
        ]
        for text, r, c, kind, cmd in layout:
            font = (theme.UI, 16) if kind == "num" else (theme.UI, 15)
            if text == "=":
                font = (theme.UI, 18, "bold")
            theme.grid_button(pad, text, r, c, self._wrap(cmd), kind, font=font)

    def _mem_btn(self, parent: tk.Frame, text: str, col: int, cmd) -> tk.Button:
        b = tk.Button(parent, text=text, command=self._wrap(cmd), bg=theme.BG, fg=theme.MEM_FG,
                      activebackground=theme.FN_HOVER, activeforeground=theme.TEXT_PRIMARY, relief="flat",
                      bd=0, font=(theme.UI, 10), disabledforeground=theme.DISABLED_FG, takefocus=0)
        b.grid(row=0, column=col, sticky="nsew", padx=1, pady=2)
        theme.add_hover(b, theme.BG, theme.FN_HOVER)
        return b

    def _wrap(self, cmd):
        def run() -> None:
            cmd()
            self._refresh()
        return run

    def _refresh(self) -> None:
        self.expr_var.set(self.engine.expr_text)
        text = self.engine.display
        self.result_var.set(text)
        size = 32
        if len(text) > 18:
            size = 18
        elif len(text) > 12:
            size = 24
        self.result_lbl.configure(font=(theme.UI, size, "bold"))
        state = "normal" if self.engine.mem_present else "disabled"
        self._mc.configure(state=state)
        self._mr.configure(state=state)

    # ---- 鍵盤 ----
    def on_key(self, keysym: str, char: str) -> None:
        e = self.engine
        if char and char in "0123456789":
            e.input_digit(char)
        elif char in (".", ","):
            e.input_dot()
        elif char == "+":
            e.operator("+")
        elif char == "-":
            e.operator("-")
        elif char == "*":
            e.operator("*")
        elif char == "/":
            e.operator("/")
        elif char == "%":
            e.percent()
        elif keysym in ("Return", "KP_Enter") or char == "=":
            e.equals()
        elif keysym == "BackSpace":
            e.backspace()
        elif keysym == "Escape":
            e.clear_all()
        elif keysym == "Delete":
            e.clear_entry()
        else:
            return
        self._refresh()
