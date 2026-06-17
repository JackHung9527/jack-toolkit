"""工程計算機分頁 UI（可編輯運算式輸入框 + 方向鍵編輯）。"""

from __future__ import annotations

import tkinter as tk

import theme
from engine_sci import SciEngine


class ScientificFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.engine = SciEngine()
        self.top_var = tk.StringVar()             # 小算式行（上次 = 的算式）
        self.expr_var = tk.StringVar()            # 可編輯運算式
        self.angle_var = tk.StringVar(value=self.engine.angle)
        self.history: list[str] = []
        self.hist_idx: int | None = None
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        disp = tk.Frame(self, bg=theme.DISPLAY_BG)
        disp.grid(row=0, column=0, sticky="nsew", padx=4, pady=(6, 0))
        disp.columnconfigure(0, weight=1)
        tk.Label(disp, textvariable=self.top_var, anchor="e", bg=theme.DISPLAY_BG,
                 fg=theme.EXPR_FG, font=(theme.UI, 11)).grid(row=0, column=0, sticky="ew", padx=8)
        # 可編輯運算式輸入框：方向鍵 / Home / End / 點選 / 游標處插入刪除 全部原生支援
        self.expr_entry = tk.Entry(disp, textvariable=self.expr_var, justify="right",
                                   bg=theme.DISPLAY_BG, fg=theme.RESULT_FG,
                                   insertbackground=theme.RESULT_FG, relief="flat", bd=0,
                                   font=(theme.UI, 22, "bold"))
        self.expr_entry.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.focus_widget = self.expr_entry       # 切到本模式時自動聚焦
        theme.bind_numpad_decimal_fix(self.expr_entry)
        self.expr_entry.bind("<Return>", lambda _e: self._equals())
        self.expr_entry.bind("<KP_Enter>", lambda _e: self._equals())
        self.expr_entry.bind("<Up>", lambda _e: self._history(-1))
        self.expr_entry.bind("<Down>", lambda _e: self._history(1))

        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        for c in range(5):
            pad.columnconfigure(c, weight=1, uniform="k")
        for r in range(7):
            pad.rowconfigure(r, weight=1, uniform="k")

        self.angle_btn = tk.Button(pad, textvariable=self.angle_var, command=self._toggle_angle,
                                   bg=theme.FN_BG, fg=theme.ANGLE_FG, activebackground=theme.FN_HOVER,
                                   activeforeground=theme.ANGLE_FG, relief="flat", bd=0,
                                   font=(theme.UI, 12, "bold"), cursor="hand2", takefocus=0)
        self.angle_btn.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        theme.add_hover(self.angle_btn, theme.FN_BG, theme.FN_HOVER)

        self._special(pad, "(", 0, 1, lambda: self._insert("(", "lp"))
        self._special(pad, ")", 0, 2, lambda: self._insert(")", "rp"))
        self._special(pad, "CE", 0, 3, self._ce)
        self._special(pad, "C", 0, 4, self._clear)

        # (text, r, c, frag, cat)
        frags = [
            ("x²", 1, 0, "^2", "op"), ("xʸ", 1, 1, "^", "op"), ("√x", 1, 2, "√(", "func"),
            ("n!", 1, 3, "!", "op"), ("⌫", 1, 4, None, "bs"),
            ("sin", 2, 0, "sin(", "func"), ("cos", 2, 1, "cos(", "func"), ("tan", 2, 2, "tan(", "func"),
            ("ln", 2, 3, "ln(", "func"), ("÷", 2, 4, "÷", "op"),
            ("π", 3, 0, "π", "val"), ("7", 3, 1, "7", "num"), ("8", 3, 2, "8", "num"),
            ("9", 3, 3, "9", "num"), ("×", 3, 4, "×", "op"),
            ("e", 4, 0, "e", "val"), ("4", 4, 1, "4", "num"), ("5", 4, 2, "5", "num"),
            ("6", 4, 3, "6", "num"), ("−", 4, 4, "−", "op"),
            ("log", 5, 0, "log(", "func"), ("1", 5, 1, "1", "num"), ("2", 5, 2, "2", "num"),
            ("3", 5, 3, "3", "num"), ("+", 5, 4, "+", "op"),
            ("eˣ", 6, 0, "exp(", "func"), ("±", 6, 1, "−", "op"), ("0", 6, 2, "0", "num"),
            (".", 6, 3, ".", "num"), ("=", 6, 4, None, "eq"),
        ]
        for text, r, c, frag, cat in frags:
            if cat == "bs":
                cmd, kind = self._backspace, "fn"
            elif cat == "eq":
                cmd, kind = self._equals, "eq"
            elif cat == "num":
                cmd, kind = (lambda f=frag: self._insert(f, "num")), "num"
            else:
                cmd, kind = (lambda f=frag, ca=cat: self._insert(f, ca)), "fn"
            font = (theme.UI, 16) if cat == "num" else (theme.UI, 13)
            if cat == "eq":
                font = (theme.UI, 18, "bold")
            theme.grid_button(pad, text, r, c, cmd, kind, font=font)

    def _special(self, parent, text, r, c, cmd) -> None:
        theme.grid_button(parent, text, r, c, cmd, "fn", font=(theme.UI, 13))

    # ---- 行為 ----
    def _insert(self, frag: str, cat: str) -> None:
        e = self.expr_entry
        # 在游標前緊鄰數字/右括/常數時，插入函式/常數/左括前補乘號
        if cat in ("val", "func", "lp"):
            pos = e.index("insert")
            text = e.get()
            if pos > 0 and (text[pos - 1].isdigit() or text[pos - 1] in ").πe"):
                e.insert("insert", "×")
        e.insert("insert", frag)
        e.focus_set()

    def _backspace(self) -> None:
        e = self.expr_entry
        if e.selection_present():
            e.delete("sel.first", "sel.last")
        else:
            pos = e.index("insert")
            if pos > 0:
                e.delete(pos - 1, pos)
        e.focus_set()

    def _ce(self) -> None:
        self.expr_var.set("")
        self.expr_entry.focus_set()

    def _clear(self) -> None:
        self.expr_var.set("")
        self.top_var.set("")
        self.expr_entry.focus_set()

    def _toggle_angle(self) -> None:
        self.engine.toggle_angle()
        self.angle_var.set(self.engine.angle)
        self.expr_entry.focus_set()

    def _equals(self) -> str:
        s = self.expr_var.get().strip()
        if not s:
            return "break"
        try:
            res = self.engine.eval_str(s)
        except Exception:
            self.top_var.set("錯誤")
            return "break"
        if not self.history or self.history[-1] != s:
            self.history.append(s)
        self.hist_idx = None
        self.top_var.set(s + " =")
        self.expr_var.set(res)
        self.expr_entry.icursor("end")
        self.expr_entry.xview_moveto(1.0)
        return "break"

    def _history(self, direction: int) -> str:
        if not self.history:
            return "break"
        if self.hist_idx is None:
            self.hist_idx = len(self.history)
        self.hist_idx = max(0, min(len(self.history), self.hist_idx + direction))
        if self.hist_idx >= len(self.history):
            self.expr_var.set("")
        else:
            self.expr_var.set(self.history[self.hist_idx])
        self.expr_entry.icursor("end")
        return "break"

    # 全域鍵盤：本模式靠輸入框原生處理，不需攔截
    def on_key(self, keysym: str, char: str) -> None:
        return
