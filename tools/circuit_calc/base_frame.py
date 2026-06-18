"""計算分頁共用基底：標準版面（標題 / 參考電路圖 / 輸入 / 結果）與輸入 helper。

子類別覆寫：
  TITLE / HINT / DIAGRAM(寬,高 或 None) / RESULT_HEIGHT / PROMPT
  build()          —— 用 add_row / add_plain_row / add_mode 加輸入
  draw_diagram(cv) —— 在 canvas 上畫參考電路圖（DIAGRAM 非 None 才會呼叫）
  compute()        —— 讀值、算、用 self.show() 輸出；缺值丟 Incomplete、錯誤丟 ValueError
"""

from __future__ import annotations

import tkinter as tk

import theme
from units import ValueEntry


class Incomplete(Exception):
    """欄位尚未填完整（非錯誤，只是還不能算）。"""


class CalcFrame(tk.Frame):
    TITLE = ""
    HINT = ""
    DIAGRAM: tuple[int, int] | None = None
    RESULT_HEIGHT = 9
    PROMPT = "(請完整輸入各欄位)"

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.ve: dict[str, ValueEntry] = {}
        self.plain: dict[str, tk.StringVar] = {}
        self._rows: dict[str, tk.Frame] = {}
        self._next = 0
        self.focus_widget = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
        pad.columnconfigure(0, weight=1)

        r = 0
        theme.title_label(pad, self.TITLE).grid(row=r, column=0, sticky="w"); r += 1
        if self.HINT:
            theme.hint_label(pad, self.HINT).grid(row=r, column=0, sticky="w", pady=(4, 4)); r += 1
        self.canvas: tk.Canvas | None = None
        if self.DIAGRAM is not None:
            w, h = self.DIAGRAM
            self.canvas = tk.Canvas(pad, width=w, height=h, bg=theme.ENTRY_BG, bd=0,
                                    highlightthickness=1, highlightbackground=theme.PANEL)
            self.canvas.grid(row=r, column=0, sticky="w", pady=(4, 8)); r += 1
        self.inbox = tk.Frame(pad, bg=theme.BG)
        self.inbox.grid(row=r, column=0, sticky="w", pady=(0, 6)); r += 1
        self.out = theme.make_result_text(pad, height=self.RESULT_HEIGHT)
        self.out.grid(row=r, column=0, sticky="nsew", pady=(2, 0))
        pad.rowconfigure(r, weight=1)

        self.build()
        if self.canvas is not None:
            self.draw_diagram(self.canvas)
        self.recompute()

    # ---------------- 輸入 helper ----------------
    def _claim(self, at: int | None) -> int:
        if at is not None:
            return at
        row = self._next
        self._next += 1
        return row

    def add_row(self, key: str, label: str, quantity_key: str, default_text: str = "",
                default_unit: str | None = None, at: int | None = None,
                label_width: int = 12) -> ValueEntry:
        rowf = tk.Frame(self.inbox, bg=theme.BG)
        rowf.grid(row=self._claim(at), column=0, sticky="w", pady=3)
        tk.Label(rowf, text=label, bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=label_width, anchor="e").pack(side="left", padx=(0, 8))
        ve = ValueEntry(rowf, quantity_key, default_text, default_unit, on_change=self.recompute)
        ve.pack(side="left")
        self.ve[key] = ve
        self._rows[key] = rowf
        if self.focus_widget is None:
            self.focus_widget = ve.entry
        return ve

    def add_plain_row(self, key: str, label: str, default: str = "", suffix: str = "",
                      at: int | None = None, label_width: int = 12) -> tk.Entry:
        rowf = tk.Frame(self.inbox, bg=theme.BG)
        rowf.grid(row=self._claim(at), column=0, sticky="w", pady=3)
        tk.Label(rowf, text=label, bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=label_width, anchor="e").pack(side="left", padx=(0, 8))
        var = tk.StringVar(value=default)
        ent = theme.make_entry(rowf, var, width=11)
        ent.pack(side="left", ipady=3)
        if suffix:
            tk.Label(rowf, text=suffix, bg=theme.BG, fg=theme.TEXT_SECONDARY,
                     font=(theme.UI, 10)).pack(side="left", padx=(5, 0))
        var.trace_add("write", lambda *_: self.recompute())
        self.plain[key] = var
        self._rows[key] = rowf
        if self.focus_widget is None:
            self.focus_widget = ent
        return ent

    def add_mode(self, var: tk.StringVar, options: list[tuple[str, str]], command,
                 label: str = "模式：", at: int | None = None) -> tk.Frame:
        rowf = tk.Frame(self.inbox, bg=theme.BG)
        rowf.grid(row=self._claim(at), column=0, sticky="w", pady=(0, 4))
        tk.Label(rowf, text=label, bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        for val, txt in options:
            tk.Radiobutton(
                rowf, text=txt, value=val, variable=var, command=command,
                bg=theme.BG, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                activebackground=theme.BG, activeforeground=theme.TEXT_PRIMARY,
                font=(theme.UI, 10), highlightthickness=0, bd=0,
            ).pack(side="left", padx=4)
        return rowf

    # ---------------- 取值 helper ----------------
    def base(self, *keys: str) -> list[float]:
        """取多個 ValueEntry 的基本單位值；缺值丟 Incomplete、格式錯丟 ValueError。"""
        out = []
        for k in keys:
            v = self.ve[k].get_base()
            if v is None:
                if self.ve[k].is_invalid():
                    raise ValueError(f"{k} 數值格式錯誤")
                raise Incomplete()
            out.append(v)
        return out

    def opt_base(self, key: str) -> float | None:
        """可選欄位：空白回 None；格式錯丟 ValueError。"""
        if self.ve[key].is_invalid():
            raise ValueError(f"{key} 數值格式錯誤")
        return self.ve[key].get_base()

    def pnum(self, *keys: str) -> list[float]:
        out = []
        for k in keys:
            t = self.plain[k].get().strip()
            if not t:
                raise Incomplete()
            try:
                out.append(float(t))
            except ValueError:
                raise ValueError(f"{k} 數值格式錯誤")
        return out

    def show(self, text: str) -> None:
        theme.set_text(self.out, text)

    def recompute(self) -> None:
        try:
            self.compute()
        except Incomplete:
            self.show(self.PROMPT)
        except ValueError as exc:
            self.show(f"輸入錯誤：{exc}")

    # ---------------- 子類別覆寫 ----------------
    def build(self) -> None:  # pragma: no cover - 由子類別實作
        raise NotImplementedError

    def draw_diagram(self, cv: tk.Canvas) -> None:
        pass

    def compute(self) -> None:  # pragma: no cover - 由子類別實作
        raise NotImplementedError
