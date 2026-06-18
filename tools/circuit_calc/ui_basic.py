"""基礎電學包：歐姆定律 / 串並聯電阻 / LED 限流電阻。"""

from __future__ import annotations

import tkinter as tk

import engine
import schematic as sch
from base_frame import CalcFrame, Incomplete
from units import format_eng


class OhmFrame(CalcFrame):
    TITLE = "歐姆定律 / 功率"
    HINT = "V = I × R   P = V × I = I²R = V²/R。任意填兩格，自動算其餘兩格。"
    DIAGRAM = (390, 150)
    PROMPT = "(請填入 V / I / R / P 之中任兩格)"

    def build(self) -> None:
        self.add_row("v", "電壓 V", "voltage", "", "V")
        self.add_row("i", "電流 I", "current", "", "mA")
        self.add_row("r", "電阻 R", "resistance", "", "kΩ")
        self.add_row("p", "功率 P", "power", "", "mW")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        tb, bb = sch.battery_v(cv, 70, 75, "V")
        sch.wire(cv, 70, 62, 70, 40, 320, 40)
        rt, rb = sch.resistor_v(cv, 320, 75, "R")
        sch.wire(cv, 320, 40, *rt)
        sch.wire(cv, *rb, 320, 112, 70, 112, 70, 88)
        sch.arrow(cv, 150, 40, 205, 40, "I")
        sch.text(cv, 195, 130, "P = V · I", small=True, color=sch.LBL)

    def compute(self) -> None:
        vals = {k: self.opt_base(k) for k in ("v", "i", "r", "p")}
        provided = {k: v for k, v in vals.items() if v is not None}
        if len(provided) < 2:
            raise Incomplete()
        res = engine.ohms_law(**{k: vals[k] for k in ("v", "i", "r", "p")})
        lines = [
            f"電壓 V = {format_eng(res['v'], 'V')}",
            f"電流 I = {format_eng(res['i'], 'A')}",
            f"電阻 R = {format_eng(res['r'], 'Ω')}",
            f"功率 P = {format_eng(res['p'], 'W')}",
        ]
        self.show("\n".join(lines))


class SeriesParallelFrame(CalcFrame):
    TITLE = "串 / 並聯電阻"
    HINT = "輸入多顆電阻（空白略過）。串聯：相加；並聯：倒數和的倒數。"
    DIAGRAM = (390, 150)
    PROMPT = "(請至少輸入一顆電阻)"
    _N = 6

    def build(self) -> None:
        self.mode = tk.StringVar(value="series")
        self.add_mode(self.mode, [("series", "串聯"), ("parallel", "並聯")], self._on_mode)
        for k in range(1, self._N + 1):
            default = "10" if k <= 2 else ""
            self.add_row(f"r{k}", f"R{k}", "resistance", default, "kΩ")

    def _on_mode(self) -> None:
        if self.canvas is not None:
            self.canvas.delete("all")
            self.draw_diagram(self.canvas)
        self.recompute()

    def draw_diagram(self, cv: tk.Canvas) -> None:
        if self.mode.get() == "series":
            y = 72
            sch.node(cv, 36, y, "A", anchor="n")
            xs = [95, 185, 275]
            prev = (36, y)
            for i, cx in enumerate(xs):
                lt, rt = sch.resistor_h(cv, cx, y, f"R{i + 1}")
                sch.wire(cv, prev[0], y, lt[0], y)
                prev = rt
            sch.wire(cv, prev[0], y, 330, y)
            sch.text(cv, 352, y, "…", bold=True)
            sch.node(cv, 360, y, "B", anchor="n")
        else:
            top, bot = 45, 116
            sch.wire(cv, 60, top, 300, top)
            sch.wire(cv, 60, bot, 300, bot)
            sch.node(cv, 60, top, "A", anchor="s")
            sch.node(cv, 60, bot, "B", anchor="n")
            for i, cx in enumerate((110, 180, 250)):
                rt, rb = sch.resistor_v(cv, cx, 80, f"R{i + 1}")
                sch.wire(cv, cx, top, *rt)
                sch.wire(cv, *rb, cx, bot)
            sch.text(cv, 320, 80, "…", bold=True)

    def compute(self) -> None:
        values = []
        for k in range(1, self._N + 1):
            v = self.opt_base(f"r{k}")
            if v is not None:
                values.append(v)
        if not values:
            raise Incomplete()
        if self.mode.get() == "series":
            req = engine.series_resistance(values)
            law = "串聯（相加）"
        else:
            req = engine.parallel_resistance(values)
            law = "並聯（倒數和的倒數）"
        std = engine.nearest_e_series(req, "E24")
        lines = [
            f"等效電阻 Req = {format_eng(req, 'Ω')}   [{law}]",
            f"使用電阻數   = {len(values)} 顆",
            f"最接近 E24   = {format_eng(std, 'Ω')}",
        ]
        self.show("\n".join(lines))


class LedFrame(CalcFrame):
    TITLE = "LED 限流電阻"
    HINT = "R = (Vsupply − Vf) / If。Vf 為 LED 順向壓降、If 為目標順向電流。"
    DIAGRAM = (390, 150)
    PROMPT = "(請輸入 Vsupply、Vf、If)"

    def build(self) -> None:
        self.add_row("vs", "Vsupply", "voltage", "5", "V")
        self.add_row("vf", "LED Vf", "voltage", "2", "V")
        self.add_row("if_", "目標 If", "current", "10", "mA")

    def draw_diagram(self, cv: tk.Canvas) -> None:
        y = 70
        sch.node(cv, 42, y, "Vsupply", anchor="s")
        lt, rt = sch.resistor_h(cv, 110, y, "R")
        sch.wire(cv, 42, y, lt[0], y)
        la, lc = sch.led_h(cv, 205, y, "LED")
        sch.wire(cv, rt[0], y, la[0], y)
        sch.wire(cv, lc[0], y, 295, y, 295, 105)
        sch.ground(cv, 295, 105)
        sch.arrow(cv, 235, y, 275, y, "If")

    def compute(self) -> None:
        vs, vf, i_f = self.base("vs", "vf", "if_")
        res = engine.led_resistor(vs, vf, i_f)
        std = engine.nearest_e_series(res["r"], "E24")
        actual_if = (vs - vf) / std
        lines = [
            f"限流電阻 R   = {format_eng(res['r'], 'Ω')}",
            f"最接近 E24   = {format_eng(std, 'Ω')}"
            f"  → 實際 If {format_eng(actual_if, 'A')}",
            "",
            f"電阻功耗 P_R = {format_eng(res['p_r'], 'W')}",
            f"LED 功耗     = {format_eng(res['p_led'], 'W')}",
        ]
        self.show("\n".join(lines))
