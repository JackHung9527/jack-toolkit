"""IEEE 754 浮點數解析分頁 UI。"""

from __future__ import annotations

import tkinter as tk

import theme
import float_defs


class FloatFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.mode = tk.StringVar(value="value")   # value(數值→位元) / hex(HEX→數值)
        self.hex_width = tk.IntVar(value=32)
        self.input_var = tk.StringVar(value="3.14159")
        self._build()
        self._compute()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(5, weight=1)

        tk.Label(pad, text="IEEE 754 浮點數解析", bg=theme.BG, fg=theme.TEXT_PRIMARY,
                 font=(theme.UI, 16, "bold")).grid(row=0, column=0, sticky="w")

        mrow = tk.Frame(pad, bg=theme.BG)
        mrow.grid(row=1, column=0, sticky="w", pady=(10, 2))
        tk.Label(mrow, text="方向：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        for val, label in (("value", "數值 → 位元"), ("hex", "HEX → 數值")):
            tk.Radiobutton(mrow, text=label, value=val, variable=self.mode, command=self._on_mode,
                           bg=theme.BG, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                           activebackground=theme.BG, activeforeground=theme.TEXT_PRIMARY,
                           font=(theme.UI, 10), highlightthickness=0, bd=0).pack(side="left", padx=4)
        self.wbox = tk.Frame(mrow, bg=theme.BG)
        self.wbox.pack(side="left", padx=(12, 0))
        for w in (32, 64):
            tk.Radiobutton(self.wbox, text=str(w) + " 位元", value=w, variable=self.hex_width,
                           command=self._compute, bg=theme.BG, fg=theme.TEXT_PRIMARY,
                           selectcolor=theme.SELECT_BG, activebackground=theme.BG,
                           activeforeground=theme.TEXT_PRIMARY, font=(theme.UI, 10),
                           highlightthickness=0, bd=0).pack(side="left", padx=2)

        ent = tk.Entry(pad, textvariable=self.input_var, bg=theme.ENTRY_BG, fg=theme.ENTRY_FG,
                       insertbackground=theme.ENTRY_FG, relief="flat", font=(theme.MONO, 14))
        ent.grid(row=2, column=0, sticky="ew", ipady=6, pady=(4, 8))
        self.focus_widget = ent  # 切到本模式時自動聚焦此輸入框
        theme.bind_numpad_decimal_fix(ent)  # 修數字鍵盤小數點被當成 Delete 的問題
        self.input_var.trace_add("write", lambda *_: self._compute())

        self.out = tk.Text(pad, height=16, bg=theme.ENTRY_BG, fg=theme.TEXT_PRIMARY, relief="flat",
                           font=(theme.MONO, 11), wrap="word", padx=10, pady=8,
                           highlightthickness=1, highlightbackground=theme.PANEL)
        self.out.grid(row=5, column=0, sticky="nsew")
        self.out.configure(state="disabled")
        self._on_mode()

    def _on_mode(self) -> None:
        if self.mode.get() == "hex":
            self.wbox.pack(side="left", padx=(12, 0))
        else:
            self.wbox.pack_forget()
        self._compute()

    def _set_text(self, text: str) -> None:
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.configure(state="disabled")

    @staticmethod
    def _panel(view: float_defs.FloatView) -> str:
        s, e, m = view.bin_groups()
        lines = [
            f"=== float{view.width} ===",
            f"儲存值      : {float_defs.stored_repr(view.stored)}",
            f"類別        : {view.category}",
            f"十六進位    : {view.hex_str()}",
            f"符號 sign   : {s}  ({'−' if view.sign else '+'})",
            f"指數 exp    : {e}  raw={view.exp_raw} 去偏移={view.exp_unbiased}",
            f"尾數 mant   : {m}",
        ]
        return "\n".join(lines)

    def _compute(self) -> None:
        text = self.input_var.get().strip()
        if not text:
            self._set_text("(請輸入)")
            return
        if self.mode.get() == "value":
            try:
                val = float(text)
            except ValueError:
                self._set_text("數值格式錯誤")
                return
            v32 = float_defs.from_value(val, 32)
            v64 = float_defs.from_value(val, 64)
            self._set_text(self._panel(v32) + "\n\n" + self._panel(v64))
        else:
            cleaned = text.lower().replace("0x", "").replace(" ", "").replace("_", "")
            try:
                bits = int(cleaned, 16)
            except ValueError:
                self._set_text("HEX 格式錯誤")
                return
            width = self.hex_width.get()
            view = float_defs.from_bits(bits, width)
            self._set_text(self._panel(view))

    def on_key(self, keysym: str, char: str) -> None:
        return
