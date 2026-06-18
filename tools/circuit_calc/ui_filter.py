"""濾波 / 時間包：RC/RL 濾波 / LC 諧振 / 555 計時器。"""

from __future__ import annotations

import tkinter as tk

import engine
import schematic as sch
from base_frame import CalcFrame
from units import format_eng


class RcRlFrame(CalcFrame):
    TITLE = "RC / RL 濾波"
    HINT = "RC：τ=RC、fc=1/(2πRC)。RL：τ=L/R、fc=R/(2πL)。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 R 與對應的 C 或 L)"

    def build(self) -> None:
        self.mode = tk.StringVar(value="rc")
        self.add_mode(self.mode, [("rc", "RC"), ("rl", "RL")], self._on_mode)
        self.add_row("r", "電阻 R", "resistance", "1", "kΩ")
        self.add_row("c", "電容 C", "capacitance", "100", "nF")
        self.add_row("l", "電感 L", "inductance", "100", "µH")

    def _on_mode(self) -> None:
        if self.mode.get() == "rc":
            self._rows["c"].grid()
            self._rows["l"].grid_remove()
        else:
            self._rows["l"].grid()
            self._rows["c"].grid_remove()
        if self.canvas is not None:
            self.canvas.delete("all")
            self.draw_diagram(self.canvas)
        self.recompute()

    def draw_diagram(self, cv: tk.Canvas) -> None:
        y = 58
        sch.node(cv, 40, y, "Vin", anchor="s")
        if self.mode.get() == "rc":
            lt, rt = sch.resistor_h(cv, 105, y, "R")
        else:
            lt, rt = sch.inductor_h(cv, 105, y, "L")
        sch.wire(cv, 40, y, lt[0], y)
        vx = 195
        sch.wire(cv, rt[0], y, vx, y)
        sch.node(cv, vx, y, "Vout", anchor="s")
        if self.mode.get() == "rc":
            top, bot = sch.cap_v(cv, vx, 95, "C")
        else:
            top, bot = sch.resistor_v(cv, vx, 95, "R")
            sch.text(cv, vx + 14, 95, "", anchor="w")
        sch.wire(cv, vx, y, *top)
        sch.wire(cv, *bot, vx, 128)
        sch.ground(cv, vx, 128)

    def compute(self) -> None:
        if self.mode.get() == "rc":
            r, c = self.base("r", "c")
            tau = r * c
            fc = engine.rc_cutoff(r, c)
            label = "RC 低通"
        else:
            r, l = self.base("r", "l")
            tau = l / r
            fc = engine.rl_cutoff(r, l)
            label = "RL 低通"
        lines = [
            f"時間常數 τ = {format_eng(tau, 's')}   [{label}]",
            f"截止頻率 fc = {format_eng(fc, 'Hz')}",
            f"5τ 穩定時間 = {format_eng(5 * tau, 's')}  (≈ 達 99.3%)",
        ]
        self.show("\n".join(lines))


class LcFrame(CalcFrame):
    TITLE = "LC 諧振頻率"
    HINT = "f₀ = 1 / (2π√(LC))。並聯 / 串聯諧振頻率相同。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 L 與 C)"

    def build(self) -> None:
        self.add_row("l", "電感 L", "inductance", "10", "µH")
        self.add_row("c", "電容 C", "capacitance", "100", "pF")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        top, bot = 52, 116
        sch.wire(cv, 160, top, 240, top)
        sch.wire(cv, 160, bot, 240, bot)
        lt, lb = sch.inductor_v(cv, 160, 84, "L")
        sch.wire(cv, 160, top, *lt)
        sch.wire(cv, *lb, 160, bot)
        ct, cbm = sch.cap_v(cv, 240, 84, "C")
        sch.wire(cv, 240, top, *ct)
        sch.wire(cv, *cbm, 240, bot)
        sch.wire(cv, 200, top, 200, 38)
        sch.wire(cv, 200, bot, 200, 130)
        sch.node(cv, 200, 38, "f₀", anchor="s")

    def compute(self) -> None:
        l, c = self.base("l", "c")
        f0 = engine.lc_resonance(l, c)
        omega = 2 * 3.141592653589793 * f0
        lines = [
            f"諧振頻率 f₀ = {format_eng(f0, 'Hz')}",
            f"角頻率 ω₀   = {format_eng(omega, '')}rad/s",
        ]
        self.show("\n".join(lines))


class Timer555Frame(CalcFrame):
    TITLE = "555 計時器（astable）"
    HINT = "f = 1.44 / ((R1 + 2R2)·C)。ton=0.693(R1+R2)C、toff=0.693·R2·C。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 R1、R2、C)"

    def build(self) -> None:
        self.add_row("r1", "R1", "resistance", "10", "kΩ")
        self.add_row("r2", "R2", "resistance", "47", "kΩ")
        self.add_row("c", "C", "capacitance", "100", "nF")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        sch.block(cv, 36, 55, 108, 105, "555")
        sch.wire(cv, 108, 80, 140, 80)
        sch.text(cv, 124, 70, "OUT", small=True)
        x, yt, yb, w = 140, 50, 105, 220
        sch.square_wave(cv, x, yt, yb, w, duty=0.66, periods=2)
        pw = w / 2
        sch.text(cv, x + pw * 0.33, 40, "ton", small=True, color=sch.HOT)
        sch.text(cv, x + pw * 0.83, 118, "toff", small=True, color=sch.HOT)

    def compute(self) -> None:
        r1, r2, c = self.base("r1", "r2", "c")
        res = engine.timer555_astable(r1, r2, c)
        lines = [
            f"頻率 f   = {format_eng(res['freq'], 'Hz')}",
            f"週期 T   = {format_eng(res['period'], 's')}",
            f"ton      = {format_eng(res['t_high'], 's')}",
            f"toff     = {format_eng(res['t_low'], 's')}",
            f"占空比   = {res['duty'] * 100:.2f} %",
        ]
        self.show("\n".join(lines))
