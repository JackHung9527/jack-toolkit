"""分壓電阻電壓計算分頁。

電路：Vin --[R1]-- Vout --[R2]-- GND。三種模式：
  正向     已知 Vin / R1 / R2 -> 求 Vout（含電流、各電阻功耗）
  反推 R2  已知 Vin / 目標 Vout / R1 -> 求 R2（附最接近 E24 標準值與驗算）
  反推 R1  已知 Vin / 目標 Vout / R2 -> 求 R1（同上）
"""

from __future__ import annotations

import tkinter as tk

import engine
import schematic as sch
import theme
from units import ValueEntry, format_eng


class DividerFrame(tk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, bg=theme.BG)
        self.mode = tk.StringVar(value="forward")
        self._build()
        self._apply_mode()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        pad = tk.Frame(self, bg=theme.BG)
        pad.grid(row=0, column=0, sticky="nsew", padx=12, pady=10)
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(6, weight=1)

        theme.title_label(pad, "分壓電阻電壓計算").grid(row=0, column=0, sticky="w")
        theme.hint_label(
            pad, "電路：Vin ──[ R1 ]──◆ Vout ──[ R2 ]── GND   （Vout 取在 R2 上端）",
        ).grid(row=1, column=0, sticky="w", pady=(4, 6))

        canvas = tk.Canvas(pad, width=390, height=140, bg=theme.ENTRY_BG, bd=0,
                           highlightthickness=1, highlightbackground=theme.PANEL)
        canvas.grid(row=2, column=0, sticky="w", pady=(2, 8))
        self._draw_diagram(canvas)

        # 模式選擇
        mrow = tk.Frame(pad, bg=theme.BG)
        mrow.grid(row=3, column=0, sticky="w", pady=(0, 6))
        tk.Label(mrow, text="模式：", bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 10)).pack(side="left")
        for val, label in (("forward", "求 Vout"), ("solve_r2", "反推 R2"), ("solve_r1", "反推 R1")):
            tk.Radiobutton(
                mrow, text=label, value=val, variable=self.mode, command=self._apply_mode,
                bg=theme.BG, fg=theme.TEXT_PRIMARY, selectcolor=theme.SELECT_BG,
                activebackground=theme.BG, activeforeground=theme.TEXT_PRIMARY,
                font=(theme.UI, 10), highlightthickness=0, bd=0,
            ).pack(side="left", padx=4)

        # 輸入區
        inputs = tk.Frame(pad, bg=theme.BG)
        inputs.grid(row=4, column=0, sticky="w", pady=(2, 8))
        self.ve: dict[str, ValueEntry] = {}
        self.rows: dict[str, tk.Frame] = {}
        self._make_row(inputs, "vin", "Vin", "voltage", "5", "V")
        self._make_row(inputs, "vout", "目標 Vout", "voltage", "2.5", "V")
        self._make_row(inputs, "r1", "R1", "resistance", "10", "kΩ")
        self._make_row(inputs, "r2", "R2", "resistance", "10", "kΩ")
        self.inputs = inputs
        self.focus_widget = self.ve["vin"].entry

        self.out = theme.make_result_text(pad, height=9)
        self.out.grid(row=6, column=0, sticky="nsew", pady=(2, 0))

    def _draw_diagram(self, cv: tk.Canvas) -> None:
        y = 58
        sch.node(cv, 40, y, "Vin", anchor="s")
        l1, r1 = sch.resistor_h(cv, 110, y, "R1")
        sch.wire(cv, 40, y, l1[0], y)
        vx = 200
        sch.wire(cv, r1[0], y, vx, y)
        sch.node(cv, vx, y, "Vout", anchor="s")
        rt, rb = sch.resistor_v(cv, vx, 95, "R2")
        sch.wire(cv, vx, y, *rt)
        sch.wire(cv, *rb, vx, 122)
        sch.ground(cv, vx, 122)

    def _make_row(self, parent: tk.Widget, key: str, label: str,
                  quantity_key: str, default_text: str, default_unit: str) -> None:
        row = tk.Frame(parent, bg=theme.BG)
        tk.Label(row, text=label, bg=theme.BG, fg=theme.TEXT_SECONDARY,
                 font=(theme.UI, 11), width=10, anchor="e").pack(side="left", padx=(0, 8))
        ve = ValueEntry(row, quantity_key, default_text, default_unit, on_change=self._recompute)
        ve.pack(side="left")
        self.ve[key] = ve
        self.rows[key] = row

    def _apply_mode(self) -> None:
        visible = {
            "forward": ["vin", "r1", "r2"],
            "solve_r2": ["vin", "vout", "r1"],
            "solve_r1": ["vin", "vout", "r2"],
        }[self.mode.get()]
        for r, (key, row) in enumerate(self.rows.items()):
            if key in visible:
                row.grid(row=visible.index(key), column=0, sticky="w", pady=3)
            else:
                row.grid_forget()
        self._recompute()

    def _recompute(self) -> None:
        mode = self.mode.get()
        try:
            if mode == "forward":
                self._forward()
            elif mode == "solve_r2":
                self._solve_r2()
            else:
                self._solve_r1()
        except ValueError as exc:
            theme.set_text(self.out, f"輸入錯誤：{exc}")

    def _need(self, *keys: str) -> list[float]:
        """取出多個欄位的基本單位值；任一空白/錯誤就讓上層顯示提示。"""
        vals = []
        for k in keys:
            v = self.ve[k].get_base()
            if v is None:
                if self.ve[k].is_invalid():
                    raise ValueError(f"{k.upper()} 數值格式錯誤")
                raise _Incomplete()
            vals.append(v)
        return vals

    def _forward(self) -> None:
        try:
            vin, r1, r2 = self._need("vin", "r1", "r2")
        except _Incomplete:
            theme.set_text(self.out, "(請輸入 Vin、R1、R2)")
            return
        res = engine.divider_forward(vin, r1, r2)
        lines = [
            f"Vout       = {format_eng(res['vout'], 'V')}",
            f"分壓比     = {res['ratio']:.6g}  ({res['ratio'] * 100:.4g} %)",
            f"電流 I     = {format_eng(res['current'], 'A')}",
            "",
            f"R1 壓降    = {format_eng(res['v_r1'], 'V')}",
            f"總電阻     = {format_eng(res['total_r'], 'Ω')}",
            f"R1 功耗    = {format_eng(res['p_r1'], 'W')}",
            f"R2 功耗    = {format_eng(res['p_r2'], 'W')}",
            f"總功耗     = {format_eng(res['p_total'], 'W')}",
        ]
        theme.set_text(self.out, "\n".join(lines))

    def _solve_r2(self) -> None:
        try:
            vin, vout, r1 = self._need("vin", "vout", "r1")
        except _Incomplete:
            theme.set_text(self.out, "(請輸入 Vin、目標 Vout、R1)")
            return
        r2 = engine.divider_solve_r2(vin, vout, r1)
        self._show_solved("R2", r2, vin, r1=r1, solved="r2")

    def _solve_r1(self) -> None:
        try:
            vin, vout, r2 = self._need("vin", "vout", "r2")
        except _Incomplete:
            theme.set_text(self.out, "(請輸入 Vin、目標 Vout、R2)")
            return
        r1 = engine.divider_solve_r1(vin, vout, r2)
        self._show_solved("R1", r1, vin, r2=r2, solved="r1")

    def _show_solved(self, name: str, value: float, vin: float, *,
                     r1: float | None = None, r2: float | None = None, solved: str) -> None:
        lines = [f"{name}（理論值） = {format_eng(value, 'Ω')}"]
        if value <= 0:
            lines.append("(注意：解出非正電阻，請檢查 Vin / Vout 條件)")
            theme.set_text(self.out, "\n".join(lines))
            return
        for series in ("E24", "E96"):
            std = engine.nearest_e_series(value, series)
            if solved == "r2":
                check = engine.divider_forward(vin, r1, std)["vout"]
            else:
                check = engine.divider_forward(vin, std, r2)["vout"]
            lines.append(f"最接近 {series} = {format_eng(std, 'Ω')}"
                         f"  → 實際 Vout {format_eng(check, 'V')}")
        theme.set_text(self.out, "\n".join(lines))


class _Incomplete(Exception):
    """內部用：欄位尚未填完整，不算錯誤。"""
